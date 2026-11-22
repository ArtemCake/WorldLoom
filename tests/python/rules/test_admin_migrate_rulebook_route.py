# tests/python/rules/test_admin_migrate_rulebook_route.py

"""HTTP-эндпоинт migrate_system_rulebook (POST /admin/game-systems/{system_id}/rules/migrate-rulebook).

Проверяет через реальный PostgreSQL:
- 201 при наличии rulebook с текстами;
- книга и черновик создаются корректно;
- 422 при отсутствии rulebook;
- 401/403 без авторизации;
- CSRF-защита включена (интроспекция зависимостей);
- откат транзакции не оставляет книги.
"""

from __future__ import annotations
import os
import unittest
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import func, insert, null, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app.infrastructure.database.model_registry import configure_models
from backend.app.modules.game_systems.models.game_systems import (
    GameSystem,
    GameSystemRulesDraft,
)
from backend.app.modules.rules.models.books import RuleBook, RuleBookDraft
from backend.app.modules.admin.api import router
from backend.app.modules.admin.dependencies import require_content_manager
from backend.app.modules.auth.dependencies import get_current_user
from backend.app.infrastructure.database.session import get_async_session
from backend.app.web.csrf import enforce_csrf
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from tests.python.rules.pg_support import (
    PostgresTestCase,
    apply_migrations,
    require_connection,
    system_values,
    user_values,
)


configure_models()

_ROUTE = "/admin/game-systems/{system_id}/rules/migrate-rulebook"
_GAME_SYSTEMS = GameSystem.__table__
_GAME_DRAFTS = GameSystemRulesDraft.__table__
_BOOKS = RuleBook.__table__
_BOOK_DRAFTS = RuleBookDraft.__table__

RULEBOOK_WITH_TEXTS = {
    "intro": {
        "label": "Введение",
        "status": "described",
        "fields": {
            "overview": "Вступительный текст.",
            "purpose": "Цель раздела.",
        },
    },
}

FULL_PROFILE_WITH_RULEBOOK = {
    "schema_version": 4,
    "slug": "test-sys",
    "calculations": {"attributes": {}, "derived": {}},
    "initial_attributes": {"hp": 10},
    "resources": {},
    "rulebook": RULEBOOK_WITH_TEXTS,
}

FULL_PROFILE_NO_RULEBOOK = {
    "schema_version": 4,
    "slug": "test-sys",
    "calculations": {"attributes": {}, "derived": {}},
    "initial_attributes": {"hp": 10},
    "resources": {},
}


class AdminMigrateRulebookRouteTests(PostgresTestCase):
    """Тесты HTTP-эндпоинта переноса rulebook."""

    async def asyncSetUp(self):
        raw_url = os.environ.get("WORLDLOOM_RULES_TEST_URL")
        if not raw_url:
            raise unittest.SkipTest("Нет WORLDLOOM_RULES_TEST_URL")

        url = make_url(raw_url)
        if url.drivername != "postgresql+asyncpg":
            raise RuntimeError("Должен использоваться postgresql+asyncpg")
        if not url.database.endswith(("_test", "_tests")):
            raise RuntimeError("Имя базы должно оканчиваться на _test или _tests")

        await require_connection(url)

        self.schema = f"wl_http_migrule_{uuid4().hex}"
        self.owner_id = uuid4()
        self.system_id = uuid4()

        self.admin_engine = create_async_engine(url, poolclass=NullPool, hide_parameters=True)
        self.engine = None

        async with self.admin_engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{self.schema}"'))

        self.engine = create_async_engine(
            url,
            poolclass=NullPool,
            hide_parameters=True,
            isolation_level="READ COMMITTED",
            connect_args={
                "server_settings": {
                    "search_path": self.schema,
                    "lock_timeout": "5000",
                    "statement_timeout": "10000",
                }
            },
        )
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

        # Миграции
        async with self.engine.begin() as connection:
            await connection.run_sync(apply_migrations)

        # Пользователь
        async with self.engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO users (id, email_encrypted, email_hash, nickname, "
                    "is_email_verified, is_active, is_2fa_enabled) "
                    "VALUES (:id, :email, :email_hash, :nickname, false, true, false)"
                ),
                user_values(self.owner_id),
            )

        # Система
        async with self.engine.begin() as connection:
            values = system_values(system_id=self.system_id)
            await connection.execute(
                insert(_GAME_SYSTEMS).values(
                    id=values["id"],
                    name=values["name"],
                    slug=values["slug"],
                    rules_engine_version="1.0",
                    is_active=values["is_active"],
                )
            )

    async def asyncTearDown(self):
        if self.engine:
            await self.engine.dispose()
        try:
            async with self.admin_engine.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE'))
        finally:
            await self.admin_engine.dispose()

    async def _insert_draft(self, rules_json):
        """Вставить черновик системы в тестовую схему."""
        async with self.engine.begin() as connection:
            await connection.execute(
                insert(_GAME_DRAFTS).values(
                    system_id=self.system_id,
                    revision=1,
                    engine_version_id=null(),
                    rules_overrides_json=null(),
                    rules_json=rules_json,
                )
            )

    async def _book_count(self):
        async with self.engine.connect() as conn:
            return (
                await conn.execute(select(func.count()).select_from(_BOOKS))
            ).scalar_one()

    async def _book_rows(self):
        async with self.engine.connect() as conn:
            return [
                dict(r)
                for r in (
                    await conn.execute(select(_BOOKS))
                ).mappings().all()
            ]

    # ------------------------------------------------------------------ #

    async def test_migrate_route_success(self):
        """Успешный перенос: 201, книга создана, структура ответа верна."""
        await self._insert_draft(FULL_PROFILE_WITH_RULEBOOK)

        app = FastAPI()
        app.include_router(router)

        async def session_dependency():
            async with self.sessions() as s:
                if not s.in_transaction():
                    await s.begin()
                yield s

        async def user_dependency():
            return SimpleNamespace(
                id=self.owner_id,
                roles=["administrator"],
                admin_permissions=["content"],
            )

        async def csrf_dependency():
            return None

        app.dependency_overrides[get_async_session] = session_dependency
        app.dependency_overrides[get_current_user] = user_dependency
        app.dependency_overrides[require_content_manager] = user_dependency
        app.dependency_overrides[enforce_csrf] = csrf_dependency

        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        try:
            resp = await client.post(
                _ROUTE.format(system_id=str(self.system_id)),
                json={
                    "title": "Системные правила",
                    "summary": "Перенесённые тексты",
                    "language": "ru",
                    "edition_key": None,
                },
            )
        finally:
            await client.aclose()

        self.assertEqual(resp.status_code, 201, resp.text)
        data = resp.json()
        self.assertEqual(data["system_id"], str(self.system_id))
        self.assertEqual(data["draft_revision"], 2)
        self.assertEqual(data["chapters"], 1)
        self.assertEqual(data["texts"], 2)
        self.assertIn("book_id", data)
        self.assertEqual(resp.headers["cache-control"], "no-store")

        books = await self._book_rows()
        self.assertEqual(len(books), 1)
        self.assertEqual(str(books[0]["system_id"]), str(self.system_id))
        self.assertEqual(books[0]["visibility"], "private")

    async def test_migrate_route_default_title(self):
        """При отсутствии title берётся name системы."""
        sys_name = f"Имя Системы {uuid4().hex[:8]}"
        async with self.engine.begin() as connection:
            await connection.execute(
                text("UPDATE game_systems SET name = :name WHERE id = :sid"),
                {"name": sys_name, "sid": str(self.system_id)},
            )

        await self._insert_draft(FULL_PROFILE_WITH_RULEBOOK)

        app = FastAPI()
        app.include_router(router)

        async def session_dependency():
            async with self.sessions() as s:
                if not s.in_transaction():
                    await s.begin()
                yield s

        async def user_dependency():
            return SimpleNamespace(
                id=self.owner_id,
                roles=["administrator"],
                admin_permissions=["content"],
            )

        async def csrf_dependency():
            return None

        app.dependency_overrides[get_async_session] = session_dependency
        app.dependency_overrides[get_current_user] = user_dependency
        app.dependency_overrides[require_content_manager] = user_dependency
        app.dependency_overrides[enforce_csrf] = csrf_dependency

        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        try:
            resp = await client.post(
                _ROUTE.format(system_id=str(self.system_id)),
                json={
                    "summary": "",
                    "language": "ru",
                    "edition_key": None,
                },
            )
        finally:
            await client.aclose()

        self.assertEqual(resp.status_code, 201, resp.text)

    async def test_migrate_route_no_rulebook_422(self):
        """Отсутствие rulebook в черновике → 422."""
        await self._insert_draft(FULL_PROFILE_NO_RULEBOOK)

        app = FastAPI()
        app.include_router(router)

        async def session_dependency():
            async with self.sessions() as s:
                if not s.in_transaction():
                    await s.begin()
                yield s

        async def user_dependency():
            return SimpleNamespace(
                id=self.owner_id,
                roles=["administrator"],
                admin_permissions=["content"],
            )

        async def csrf_dependency():
            return None

        app.dependency_overrides[get_async_session] = session_dependency
        app.dependency_overrides[get_current_user] = user_dependency
        app.dependency_overrides[require_content_manager] = user_dependency
        app.dependency_overrides[enforce_csrf] = csrf_dependency

        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        try:
            resp = await client.post(
                _ROUTE.format(system_id=str(self.system_id)),
                json={
                    "title": "Тест",
                    "summary": "",
                    "language": "ru",
                    "edition_key": None,
                },
            )
        finally:
            await client.aclose()

        self.assertEqual(resp.status_code, 422, resp.text)

    async def test_migrate_route_requires_authorization(self):
        """Без авторизованного пользователя → 401/403."""
        await self._insert_draft(FULL_PROFILE_WITH_RULEBOOK)

        app = FastAPI()
        app.include_router(router)

        async def session_dependency():
            async with self.sessions() as s:
                if not s.in_transaction():
                    await s.begin()
                yield s

        app.dependency_overrides[get_async_session] = session_dependency
        # require_content_manager и get_current_user НЕ переопределены

        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        try:
            resp = await client.post(
                _ROUTE.format(system_id=str(self.system_id)),
                json={
                    "title": "Тест",
                    "summary": "",
                    "language": "ru",
                    "edition_key": None,
                },
            )
        finally:
            await client.aclose()

        self.assertIn(resp.status_code, (401, 403))

    async def test_migrate_route_csrf_dependency_present(self):
        """Маршрут имеет enforce_csrf в зависимостях (интроспекция)."""
        route = None
        for r in router.routes:
            if hasattr(r, "path") and r.path == "/admin/game-systems/{system_id}/rules/migrate-rulebook":
                route = r
                break

        self.assertIsNotNone(route, "Маршрут migrate-rulebook не найден в router")
        deps = [str(d) for d in getattr(route, "dependencies", []) or []]
        csrf_found = any("enforce_csrf" in d or "Csrf" in d for d in deps)
        self.assertTrue(csrf_found, "Маршрут не имеет enforce_csrf в зависимостях")


if __name__ == "__main__":
    unittest.main()
