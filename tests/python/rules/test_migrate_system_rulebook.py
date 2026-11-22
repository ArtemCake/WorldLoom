# tests/python/rules/test_migrate_system_rulebook.py

"""Перенос rulebook системы в отдельную книгу (этап F) — PostgreSQL.

Проверяет, что migrate_system_rulebook:
- создаёт книгу системы и заполняет рабочий черновик перенесённым содержанием;
- НЕ изменяет числовой профиль системы (черновик правил остаётся прежним);
- возвращает корректный RuleBookMigrationRead;
- откат внешней транзакции не оставляет книги и черновика;
- slug собирается из rules_json или из идентификатора системы.

create_system_book создаёт черновик книги с revision=1, поэтому
update_working_draft(expected_revision=1) оставляет итоговую revision=2.
"""

from __future__ import annotations
import os
import unittest
from uuid import uuid4

from sqlalchemy import func, insert, null, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app.infrastructure.database.model_registry import configure_models
from backend.app.modules.game_systems.models.game_systems import (
    GameSystem,
    GameSystemRulesDraft,
)
from backend.app.modules.rules import errors
from backend.app.modules.rules.models.books import RuleBook, RuleBookDraft
from backend.app.modules.rules.services.books.rulebook_service import (
    migrate_system_rulebook,
)
from tests.python.rules.pg_support import (
    USER_INSERT_SQL,
    PostgresTestCase,
    apply_migrations,
    require_connection,
    system_values,
    user_values,
)


configure_models()


_GAME_SYSTEMS = GameSystem.__table__
_GAME_DRAFTS = GameSystemRulesDraft.__table__
_BOOKS = RuleBook.__table__
_BOOK_DRAFTS = RuleBookDraft.__table__


def database_url():
    raw = os.environ.get("WORLDLOOM_RULES_TEST_URL")

    if not raw:
        raise unittest.SkipTest("Нет WORLDLOOM_RULES_TEST_URL; PostgreSQL-проверки пропущены")

    url = make_url(raw)

    if url.drivername != "postgresql+asyncpg":
        raise RuntimeError("Должен использоваться postgresql+asyncpg")

    if not url.database or not url.database.endswith(("_test", "_tests")):
        raise RuntimeError("Имя базы должно оканчиваться на _test или _tests")

    return url


# Формат rulebook: {код: {label, status, fields: {код_поля: текст}}}
RULEBOOK_CONTENT = {
    "intro": {
        "label": "Введение",
        "status": "described",
        "fields": {
            "overview": "Вступительный текст.",
            "purpose": "Цель раздела.",
        },
    },
    "combat": {
        "label": "Бой",
        "status": "described",
        "fields": {
            "action_types": "Типы действий в бою.",
        },
    },
}

# Полный профиль системы: числовая часть + текстовый раздел rulebook.
FULL_PROFILE = {
    "schema_version": 4,
    "slug": "Test System",
    "calculations": {"attributes": {}, "derived": {}},
    "initial_attributes": {"hp": 10},
    "resources": {},
    "rulebook": RULEBOOK_CONTENT,
}


class MigrateRulebookPostgreSQLTests(PostgresTestCase):
    """Интеграционные тесты migrate_system_rulebook на PostgreSQL."""

    async def asyncSetUp(self):
        url = database_url()
        await require_connection(url)
        self.schema = f"wl_migrule_{uuid4().hex}"
        self.owner_id = uuid4()
        self.system_id = uuid4()
        self.engine = None
        self.admin_engine = create_async_engine(url, poolclass=NullPool, hide_parameters=True)
        self.addAsyncCleanup(self.cleanup_database)

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

        async with self.engine.begin() as connection:
            await connection.run_sync(apply_migrations)
            await connection.execute(USER_INSERT_SQL, user_values(self.owner_id))
            values = system_values(system_id=self.system_id)
            await connection.execute(
                insert(_GAME_SYSTEMS).values(
                    id=values["id"],
                    name=values["name"],
                    slug=values["slug"],
                    rules_engine_version="1.0",
                    is_active=True,
                )
            )

    async def cleanup_database(self):
        if self.engine is not None:
            await self.engine.dispose()

        try:
            async with self.admin_engine.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE'))
        finally:
            await self.admin_engine.dispose()

    async def migrate(self, rules_json, *, title="Правила системы", summary="Системные правила"):
        async with self.sessions.begin() as session:
            return await migrate_system_rulebook(
                session,
                system_id=self.system_id,
                actor_id=self.owner_id,
                rules_json=rules_json,
                title=title,
                summary=summary,
            )

    async def book_row(self, book_id):
        async with self.sessions() as session:
            result = await session.execute(
                select(_BOOKS).where(_BOOKS.c.id == book_id)
            )
            return result.mappings().one()

    async def draft_row(self, book_id):
        async with self.sessions() as session:
            result = await session.execute(
                select(_BOOK_DRAFTS)
                .where(_BOOK_DRAFTS.c.book_id == book_id)
                .order_by(_BOOK_DRAFTS.c.revision.desc())
                .limit(1)
            )
            return result.mappings().one()

    # ------------------------------------------------------------------ #

    async def test_migrate_creates_book_and_draft(self):
        """Перенос создаёт книгу системы и заполняет её черновик."""
        result = await self.migrate(FULL_PROFILE)

        self.assertEqual(result.system_id, self.system_id)
        # create_system_book даёт revision=1, update_working_draft поднимает до 2.
        self.assertEqual(result.draft_revision, 2)
        self.assertEqual(result.chapters, 2)  # intro + combat
        self.assertEqual(result.texts, 3)     # overview, purpose, action_types

        book = await self.book_row(result.book_id)
        self.assertEqual(book["system_id"], self.system_id)
        self.assertEqual(book["visibility"], "private")
        self.assertTrue(book["is_active"])

        draft = await self.draft_row(result.book_id)
        self.assertEqual(draft["revision"], 2)
        content = draft["content_json"]
        self.assertEqual(content["title"], "Правила системы")
        self.assertEqual(content["language"], "ru")

        kinds = [node["kind"] for node in content["toc"]]
        self.assertEqual(kinds.count("chapter"), 2)
        self.assertEqual(kinds.count("text"), 3)

    async def test_migrate_preserves_system_rules_draft(self):
        """Числовой профиль системы остаётся неизменным (отчёт v2.0 §6)."""
        async with self.sessions.begin() as session:
            await session.execute(
                insert(_GAME_DRAFTS).values(
                    system_id=self.system_id,
                    revision=1,
                    engine_version_id=None,
                    rules_overrides_json=null(),
                    rules_json=FULL_PROFILE,
                )
            )

        await self.migrate(FULL_PROFILE)

        async with self.sessions() as session:
            row = (
                await session.execute(
                    select(_GAME_DRAFTS.c.revision, _GAME_DRAFTS.c.rules_json)
                    .where(_GAME_DRAFTS.c.system_id == self.system_id)
                )
            ).mappings().one()

        self.assertEqual(row["revision"], 1)
        self.assertEqual(row["rules_json"], FULL_PROFILE)

    async def test_migrate_empty_rulebook(self):
        """Пустой rulebook даёт книгу с пустым оглавлением."""
        result = await self.migrate({"schema_version": 4, "rulebook": {}})

        self.assertEqual(result.chapters, 0)
        self.assertEqual(result.texts, 0)

        draft = await self.draft_row(result.book_id)
        self.assertEqual(draft["content_json"]["toc"], [])

    async def test_migrate_no_rulebook_key(self):
        """Отсутствие ключа rulebook трактуется как пустой раздел."""
        result = await self.migrate({"schema_version": 4})

        self.assertEqual(result.chapters, 0)
        self.assertEqual(result.texts, 0)

    async def test_migrate_skips_empty_fields(self):
        """Пустые поля rulebook не становятся текстами книги."""
        rulebook = {
            "intro": {
                "label": "Введение",
                "status": "unused",
                "fields": {"overview": "   ", "purpose": ""},
            },
        }

        result = await self.migrate({"schema_version": 4, "rulebook": rulebook})

        self.assertEqual(result.chapters, 1)
        self.assertEqual(result.texts, 0)

    async def test_migrate_invalid_rules_json(self):
        """Не-словарь правил отклоняется до обращения к БД."""
        with self.assertRaises(errors.InvalidRuleBook):
            await self.migrate("not-a-dict")

        async with self.sessions() as session:
            count = (await session.execute(select(func.count()).select_from(_BOOKS))).scalar_one()

        self.assertEqual(count, 0)

    async def test_migrate_invalid_rulebook_section(self):
        """rulebook неподдерживаемого формата отклоняется."""
        with self.assertRaises(errors.InvalidRuleBook):
            await self.migrate({"schema_version": 4, "rulebook": "bad"})

    async def test_migrate_rollback_leaves_no_book(self):
        """Откат внешней транзакции не оставляет книги и черновика."""
        with self.assertRaises(ValueError):
            async with self.sessions.begin() as session:
                await migrate_system_rulebook(
                    session,
                    system_id=self.system_id,
                    actor_id=self.owner_id,
                    rules_json=FULL_PROFILE,
                    title="Правила системы",
                )
                raise ValueError("Имитация сбоя")

        async with self.sessions() as session:
            books = (await session.execute(select(func.count()).select_from(_BOOKS))).scalar_one()
            drafts = (await session.execute(select(func.count()).select_from(_BOOK_DRAFTS))).scalar_one()

        self.assertEqual(books, 0)
        self.assertEqual(drafts, 0)

    async def test_migrate_slug_from_rules(self):
        """Slug книги собирается из поля slug профиля."""
        result = await self.migrate(FULL_PROFILE)
        book = await self.book_row(result.book_id)

        self.assertEqual(book["slug"], "test-system-rules")

    async def test_migrate_slug_fallback(self):
        """Без slug используется идентификатор системы."""
        profile = dict(FULL_PROFILE)
        profile.pop("slug")

        result = await self.migrate(profile)
        book = await self.book_row(result.book_id)

        self.assertEqual(book["slug"], f"system-rules-{self.system_id.hex[:12]}")

    async def test_migrate_chapter_ordering(self):
        """Главы и тексты упорядочены по коду раздела."""
        rulebook = {
            "zebra": {"label": "Zebra", "status": "described", "fields": {}},
            "alpha": {"label": "Alpha", "status": "described", "fields": {}},
            "middle": {"label": "Middle", "status": "described", "fields": {}},
        }

        result = await self.migrate({"schema_version": 4, "rulebook": rulebook})
        draft = await self.draft_row(result.book_id)

        chapters = [node["key"] for node in draft["content_json"]["toc"] if node["kind"] == "chapter"]
        self.assertEqual(chapters, ["alpha", "middle", "zebra"])

    # ------------------------------------------------------------------ #
    # Идемпотентность (§26.3): миграция распознаёт уже перенесённые
    # записи; частичный сбой не создаёт дубликатов.
    # ------------------------------------------------------------------ #

    async def book_count(self):
        async with self.sessions() as session:
            return (
                await session.execute(select(func.count()).select_from(_BOOKS))
            ).scalar_one()

    async def create_book_only(self, rules_json):
        """Создать книгу без переноса содержания — модель частичного сбоя.

        create_system_book даёт черновик revision=1 с пустым оглавлением;
        последующий update_working_draft (перенос содержания) не выполнен.
        """
        from backend.app.modules.rules.schemas.books.books import BookContent
        from backend.app.modules.rules.schemas.system_books import SystemBookCreate
        from backend.app.modules.rules.services import system_books
        from backend.app.modules.rules.services.books.rulebook_service import (
            _system_book_slug,
        )

        slug = _system_book_slug(rules_json, self.system_id)

        async with self.sessions.begin() as session:
            created = await system_books.create_system_book(
                session,
                self.owner_id,
                SystemBookCreate(
                    slug=slug,
                    visibility="private",
                    system_id=self.system_id,
                    content=BookContent(
                        title="Правила системы",
                        summary="",
                        language="ru",
                        edition_key=None,
                        toc=[],
                    ),
                ),
            )
            return created.book.id

    async def test_repeat_migration_does_not_duplicate_book(self):
        """Повторный перенос возвращает ту же книгу и не создаёт дубликат."""
        first = await self.migrate(FULL_PROFILE)
        second = await self.migrate(FULL_PROFILE)

        self.assertEqual(first.book_id, second.book_id)
        self.assertEqual(second.draft_revision, 2)
        self.assertEqual(second.chapters, 2)
        self.assertEqual(second.texts, 3)
        self.assertEqual(await self.book_count(), 1)

    async def test_partial_failure_migration_completes(self):
        """После частичного сбоя перенос дозаполняет черновик без дубликата."""
        book_id = await self.create_book_only(FULL_PROFILE)

        # Черновик создан, но содержание не перенесено: revision=1, пустое оглавление.
        draft = await self.draft_row(book_id)
        self.assertEqual(draft["revision"], 1)
        self.assertEqual(draft["content_json"]["toc"], [])

        result = await self.migrate(FULL_PROFILE)

        # Тот же book_id, черновик дозаполнен, дубликат не создан.
        self.assertEqual(result.book_id, book_id)
        self.assertEqual(result.draft_revision, 2)
        self.assertEqual(result.chapters, 2)
        self.assertEqual(result.texts, 3)
        self.assertEqual(await self.book_count(), 1)

    async def test_completed_migration_does_not_overwrite_author_edits(self):
        """Завершённый перенос не затирает последующие правки автора."""
        from backend.app.modules.rules.schemas.books.book_working_draft import (
            BookWorkingDraftUpdate,
        )
        from backend.app.modules.rules.services.books import book_service
        from backend.app.modules.rules.services.books.rulebook_migration import (
            rulebook_to_book_draft,
        )

        first = await self.migrate(FULL_PROFILE)

        # Автор редактирует перенесённый черновик: заголовок меняется, revision растёт.
        edited = rulebook_to_book_draft(
            RULEBOOK_CONTENT,
            title="Правка автора",
            summary="Изменено автором",
        )

        async with self.sessions.begin() as session:
            await book_service.update_working_draft(
                session,
                first.book_id,
                self.owner_id,
                BookWorkingDraftUpdate(expected_revision=2, content=edited),
            )

        # Повторный перенос с исходным профилем не должен затирать правку.
        again = await self.migrate(FULL_PROFILE)

        self.assertEqual(again.book_id, first.book_id)
        self.assertEqual(again.draft_revision, 3)
        self.assertEqual(await self.book_count(), 1)

        draft = await self.draft_row(first.book_id)
        self.assertEqual(draft["revision"], 3)
        self.assertEqual(draft["content_json"]["title"], "Правка автора")


if __name__ == "__main__":
    unittest.main()
