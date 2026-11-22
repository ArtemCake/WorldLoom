# tests/python/game_systems/test_system_rules_protection.py

"""Проверки защиты неизменяемости версий правил игровой системы (§27-G).

Проверяет триггеры из модуля `system_rules_protection.py`:
- UPDATE версий → ошибка 55000;
- DELETE без параметра worldloom.removing_system_id → 55000;
- DELETE с параметром, равным system_id строки → разрешено;
- TRUNCATE таблицы → 55000;
- локальный параметр не переживает транзакцию;
- триггеры строки и TRUNCATE зарегистрированы и активны.

Каждый тест использует собственную схему без доступа к public. Схема
минимальна (две таблицы) — проверяется именно защита версий, а не вся
цепочка миграций приложения.
"""

from __future__ import annotations
import importlib.util
import os
import unittest
from pathlib import Path
from uuid import uuid4
from sqlalchemy import make_url, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.db_migrations.system_rules_protection import (
    REMOVAL_SETTING,
    UPGRADE_SQL,
)


REMOVAL_SETTING_NAME = REMOVAL_SETTING


def test_database_url() -> URL:
    """Не использовать рабочие настройки и не выводить реквизиты подключения."""
    raw = os.environ.get("WORLDLOOM_RULES_TEST_URL")

    if not raw:
        raise unittest.SkipTest("Не задан WORLDLOOM_RULES_TEST_URL; проверки PostgreSQL не выполнялись")

    try:
        url = make_url(raw)
    except Exception:
        raise RuntimeError("Некорректный формат WORLDLOOM_RULES_TEST_URL") from None

    if url.drivername != "postgresql+asyncpg":
        raise RuntimeError("Для тестов требуется подключение postgresql+asyncpg")

    if not url.database or not url.database.endswith(("_test", "_tests")):
        raise RuntimeError("Имя отдельной тестовой БД должно заканчиваться на _test или _tests")

    return url


# Не давать pytest считать вспомогательную функцию самостоятельным тестом.
test_database_url.__test__ = False


def sqlstate(error: DBAPIError):
    return getattr(error.orig, "sqlstate", None) or getattr(error.orig, "pgcode", None)


class SystemRulesProtectionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        url = test_database_url()

        self.schema = f"wl_sysprot_{uuid4().hex}"
        self.system_id = uuid4()
        self.version_id = uuid4()
        self.engine = None

        self.admin_engine = create_async_engine(url, poolclass=NullPool, hide_parameters=True)
        self.addAsyncCleanup(self.cleanup_database)

        async with self.admin_engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{self.schema}"'))

        server_settings = {
            "search_path": self.schema,
            "lock_timeout": "5000",
            "statement_timeout": "10000",
        }

        self.engine = create_async_engine(
            url,
            poolclass=NullPool,
            hide_parameters=True,
            isolation_level="READ COMMITTED",
            connect_args={"server_settings": server_settings},
        )
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

        async with self.engine.begin() as connection:
            await connection.execute(text(
                "CREATE TABLE game_systems ("
                "    id UUID PRIMARY KEY,"
                "    name TEXT,"
                "    slug TEXT,"
                "    is_active BOOLEAN NOT NULL DEFAULT true"
                ")"
            ))
            await connection.execute(text(
                "CREATE TABLE game_system_rules_versions ("
                "    id UUID PRIMARY KEY,"
                "    system_id UUID NOT NULL REFERENCES game_systems(id),"
                "    version_number INTEGER NOT NULL,"
                "    content_json JSONB NOT NULL DEFAULT '{}',"
                "    created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                ")"
            ))
            await self.seed_system(connection, self.system_id)
            await connection.execute(text(
                "INSERT INTO game_system_rules_versions (id, system_id, version_number, content_json) "
                "VALUES (:vid, :sid, 1, '{\"schema\": 1}'::jsonb)"
            ), {"vid": self.version_id, "sid": self.system_id})

            # Включаем защиту тем же SQL, что применяет миграция.
            for statement in UPGRADE_SQL:
                await connection.execute(text(statement))

    async def cleanup_database(self):
        if self.engine is not None:
            await self.engine.dispose()

        try:
            async with self.admin_engine.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE'))
        finally:
            await self.admin_engine.dispose()

    async def seed_system(self, connection, system_id):
        await connection.execute(text(
            "INSERT INTO game_systems (id, name, slug) VALUES (:id, :name, :slug)"
        ), {"id": system_id, "name": f"Система {uuid4().hex[:8]}", "slug": f"sys-{uuid4().hex}"})

    async def create_version(self, *, system_id, version_id=None):
        identifier = version_id or uuid4()

        async with self.sessions.begin() as session:
            await session.execute(text(
                "INSERT INTO game_system_rules_versions (id, system_id, version_number, content_json) "
                "VALUES (:vid, :sid, 1, '{}'::jsonb)"
            ), {"vid": identifier, "sid": system_id})

        return identifier

    async def count_versions(self, statement: str, **params) -> int:
        async with self.sessions() as session:
            result = await session.execute(text(statement), params)
            return result.scalar_one()

    async def expect_database_error(self, statement, params, expected_state: str):
        """Выполнить оператор в транзакции и проверить код ошибки PostgreSQL."""
        with self.assertRaises(DBAPIError) as caught:
            async with self.sessions.begin() as session:
                await session.execute(text(statement), params)

        self.assertEqual(
            sqlstate(caught.exception),
            expected_state,
            f"Ожидался код {expected_state}, получен {sqlstate(caught.exception)}",
        )

    async def set_removal_setting(self, session, system_id):
        await session.execute(
            text("SELECT set_config(:setting, CAST(:sid AS text), true)"),
            {"setting": REMOVAL_SETTING_NAME, "sid": str(system_id)},
        )

    # ── Триггеры зарегистрированы ──────────────────────────────────

    async def test_triggers_registered_and_enabled(self):
        """Триггеры строки и TRUNCATE должны быть созданы и активны."""
        async with self.engine.connect() as connection:
            result = await connection.execute(text(
                "SELECT t.tgname, t.tgenabled "
                "FROM pg_trigger AS t "
                "JOIN pg_class AS c ON c.oid = t.tgrelid "
                "JOIN pg_namespace AS n ON n.oid = c.relnamespace "
                "WHERE n.nspname = current_schema() "
                "AND c.relname = 'game_system_rules_versions' AND NOT t.tgisinternal"
            ))
            guards = {
                name: mode.decode() if isinstance(mode, bytes) else mode
                for name, mode in result.all()
            }

        self.assertEqual(guards.get("game_system_rules_versions_immutable"), "O")
        self.assertEqual(guards.get("game_system_rules_versions_no_truncate"), "O")

    # ── UPDATE запрещён ────────────────────────────────────────────

    async def test_update_version_rejected(self):
        """UPDATE версий правил должен отклоняться с ошибкой 55000."""
        await self.expect_database_error(
            "UPDATE game_system_rules_versions SET content_json = '{\"schema\": 2}'::jsonb WHERE id = :vid",
            {"vid": self.version_id},
            "55000",
        )

    # ── DELETE без параметра запрещён ──────────────────────────────

    async def test_delete_without_removal_setting_rejected(self):
        """DELETE версии без worldloom.removing_system_id → 55000."""
        await self.expect_database_error(
            "DELETE FROM game_system_rules_versions WHERE id = :vid",
            {"vid": self.version_id},
            "55000",
        )
        self.assertEqual(
            await self.count_versions(
                "SELECT count(*) FROM game_system_rules_versions WHERE id = :vid", vid=self.version_id
            ),
            1,
        )

    # ── DELETE с параметром разрешён ───────────────────────────────

    async def test_delete_with_removal_setting_allowed(self):
        """DELETE с параметром, равным system_id, проходит."""
        async with self.sessions.begin() as session:
            await self.set_removal_setting(session, self.system_id)
            await session.execute(
                text("DELETE FROM game_system_rules_versions WHERE id = :vid"),
                {"vid": self.version_id},
            )

        self.assertEqual(
            await self.count_versions(
                "SELECT count(*) FROM game_system_rules_versions WHERE id = :vid", vid=self.version_id
            ),
            0,
        )

    # ── Параметр не переживает транзакцию ──────────────────────────

    async def test_removal_setting_does_not_survive_transaction(self):
        """set_config(..., true) исчезает вместе с транзакцией."""
        # Первая транзакция выставляет параметр и завершается без удаления.
        async with self.sessions.begin() as session:
            await self.set_removal_setting(session, self.system_id)

        # Новая транзакция: параметра нет, поэтому удаление отклоняется.
        await self.expect_database_error(
            "DELETE FROM game_system_rules_versions WHERE id = :vid",
            {"vid": self.version_id},
            "55000",
        )

    # ── TRUNCATE запрещён ─────────────────────────────────────────

    async def test_truncate_rejected(self):
        """TRUNCATE таблицы версий правил должен отклоняться с ошибкой 55000."""
        await self.expect_database_error("TRUNCATE game_system_rules_versions", {}, "55000")

    # ── DELETE по system_id ────────────────────────────────────────

    async def test_delete_by_system_id_without_setting_rejected(self):
        """DELETE WHERE system_id без параметра → 55000."""
        await self.expect_database_error(
            "DELETE FROM game_system_rules_versions WHERE system_id = :sid",
            {"sid": self.system_id},
            "55000",
        )

    async def test_delete_by_system_id_with_setting_allowed(self):
        """DELETE WHERE system_id с параметром проходит для всех версий системы."""
        second = await self.create_version(system_id=self.system_id)

        async with self.sessions.begin() as session:
            await self.set_removal_setting(session, self.system_id)
            await session.execute(
                text("DELETE FROM game_system_rules_versions WHERE system_id = :sid"),
                {"sid": self.system_id},
            )

        remaining = await self.count_versions(
            "SELECT count(*) FROM game_system_rules_versions WHERE system_id = :sid", sid=self.system_id
        )
        self.assertEqual(remaining, 0)
        self.assertEqual(
            await self.count_versions(
                "SELECT count(*) FROM game_system_rules_versions WHERE id = :vid", vid=second
            ),
            0,
        )

    # ── Чужая версия не удаляется при параметре другой системы ─────

    async def test_delete_foreign_version_rejected(self):
        """Параметр одной системы не открывает удаление версии другой системы."""
        foreign_system = uuid4()
        foreign_version = None

        async with self.engine.begin() as connection:
            await self.seed_system(connection, foreign_system)

        foreign_version = await self.create_version(system_id=foreign_system)

        # Параметр выставлен на свою систему — чужая версия защищена.
        with self.assertRaises(DBAPIError) as caught:
            async with self.sessions.begin() as session:
                await self.set_removal_setting(session, self.system_id)
                await session.execute(
                    text("DELETE FROM game_system_rules_versions WHERE id = :vid"),
                    {"vid": foreign_version},
                )

        self.assertEqual(sqlstate(caught.exception), "55000")
        self.assertEqual(
            await self.count_versions(
                "SELECT count(*) FROM game_system_rules_versions WHERE id = :vid", vid=foreign_version
            ),
            1,
        )
