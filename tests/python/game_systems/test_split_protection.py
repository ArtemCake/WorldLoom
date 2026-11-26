# tests/python/game_systems/test_split_protection.py

"""Защита неизменяемости разделённых версий (PostgreSQL).

Проверяет, что после всей цепочки миграций триггеры защиты
навешаны на таблицы механики, текста и комплекта, а не только на
прежнюю таблицу правил. Потребители (листы, игры) читают именно эти
таблицы, поэтому их снимок обязан быть неизменяемым на уровне СУБД (§27-G).

Проверяются свойства для каждой из трёх таблиц:
- UPDATE опубликованной строки → 55000;
- DELETE без параметра worldloom.removing_system_id → 55000;
- DELETE с параметром, равным system_id строки → разрешено;
- TRUNCATE → отклонён (см. примечание ниже);
- INSERT свободен (иначе публикация была бы невозможна);
- триггеры строки и TRUNCATE зарегистрированы и активны.

Проверка TRUNCATE формулируется через CASCADE. Plain TRUNCATE на этих
таблицах отклоняется самим PostgreSQL кодом 0A000 ещё до вызова
триггера: на каждую таблицу есть входящий внешний ключ (комплект ссылается
на версии механики и текста, game_systems.current_version_id — на
комплект), а каскад PG без явного CASCADE запрещает. Каскадная форма
проходит проверку зависимостей и доходит до строки-гарда, которая и
поднимает 55000. Так проверяется именно защита публикации, а не ограничение
синтаксиса TRUNCATE.

Защита включается в единой начальной ревизии efacd4888d8b, поэтому
применяется полная цепочка, а не отдельная ревизия.
"""

from __future__ import annotations
import os
import unittest
from uuid import uuid4
from sqlalchemy import insert, make_url, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app.infrastructure.database.model_registry import configure_models

configure_models()

from backend.app.modules.game_systems.models.game_systems import GameSystem
from backend.app.modules.game_systems.models.system_versions import (
    GameSystemMechanicVersion,
    GameSystemTextVersion,
    GameSystemVersion,
)
from backend.db_migrations.system_rules_protection import REMOVAL_SETTING
from tests.python.rules.pg_support import (
    USER_INSERT_SQL,
    PostgresTestCase,
    apply_migrations,
    require_connection,
    system_values,
    user_values,
)


_SYSTEMS = GameSystem.__table__
_MECH = GameSystemMechanicVersion.__table__
_TEXT = GameSystemTextVersion.__table__
_BUNDLE = GameSystemVersion.__table__

# Таблица → (обязательные колонки вставки, ожидаемые имена триггеров).
_TABLES = {
    "game_system_mechanic_versions": _MECH,
    "game_system_text_versions": _TEXT,
    "game_system_versions": _BUNDLE,
}

MECHANIC_SNAPSHOT = {"schema_version": 1, "calculations": {"attributes": {}, "derived": {}}, "initial_attributes": {}, "resources": {}}
TEXT_SNAPSHOT = {"schema_version": 1, "chapters": {}}


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


database_url.__test__ = False


def sqlstate(error: DBAPIError):
    return getattr(error.orig, "sqlstate", None) or getattr(error.orig, "pgcode", None)


class SplitProtectionPostgreSQLTests(PostgresTestCase):
    """Реальная защита опубликованных разделённых версий."""

    async def asyncSetUp(self):
        url = database_url()
        await require_connection(url)

        self.schema = f"wl_splitprot_{uuid4().hex}"
        self.owner_id = uuid4()
        self.system_id = uuid4()
        self.mechanic_id = uuid4()
        self.text_id = uuid4()
        self.bundle_id = uuid4()
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

        # Полная цепочка: защита разделённых таблиц включается в head.
        async with self.engine.begin() as connection:
            await connection.run_sync(apply_migrations)
            await connection.execute(USER_INSERT_SQL, user_values(self.owner_id))

            values = system_values(system_id=self.system_id)
            await connection.execute(
                insert(_SYSTEMS).values(
                    id=values["id"],
                    name=values["name"],
                    slug=values["slug"],
                    rules_engine_version="1.0",
                    is_active=True,
                )
            )

            await connection.execute(
                insert(_MECH).values(
                    id=self.mechanic_id,
                    system_id=self.system_id,
                    version_number=1,
                    source_draft_revision=1,
                    mechanic_json=MECHANIC_SNAPSHOT,
                    rules_engine_version="1.0",
                )
            )
            await connection.execute(
                insert(_TEXT).values(
                    id=self.text_id,
                    system_id=self.system_id,
                    version_number=1,
                    source_draft_revision=1,
                    text_json=TEXT_SNAPSHOT,
                )
            )
            await connection.execute(
                insert(_BUNDLE).values(
                    id=self.bundle_id,
                    system_id=self.system_id,
                    version_number=1,
                    text_version_id=self.text_id,
                    mechanic_version_id=self.mechanic_id,
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

    async def expect_database_error(self, statement, params, expected_state="55000"):
        with self.assertRaises(DBAPIError) as caught:
            async with self.sessions.begin() as session:
                await session.execute(text(statement), params)

        self.assertEqual(
            sqlstate(caught.exception),
            expected_state,
            f"Ожидался код {expected_state}, получен {sqlstate(caught.exception)}",
        )

    async def count_rows(self, table, row_id) -> int:
        async with self.sessions() as session:
            result = await session.execute(
                select(table.c.id).where(table.c.id == row_id)
            )
            return len(result.all())

    async def set_removal_setting(self, session, system_id):
        await session.execute(
            text("SELECT set_config(:setting, CAST(:sid AS text), true)"),
            {"setting": REMOVAL_SETTING, "sid": str(system_id)},
        )

    # ── UPDATE отклоняется на каждой таблице ────────────────────────

    async def test_update_mechanic_version_rejected(self):
        await self.expect_database_error(
            "UPDATE game_system_mechanic_versions SET version_number = 99 WHERE id = :vid",
            {"vid": self.mechanic_id},
        )

    async def test_update_text_version_rejected(self):
        await self.expect_database_error(
            "UPDATE game_system_text_versions SET version_number = 99 WHERE id = :vid",
            {"vid": self.text_id},
        )

    async def test_update_bundle_rejected(self):
        await self.expect_database_error(
            "UPDATE game_system_versions SET version_number = 99 WHERE id = :vid",
            {"vid": self.bundle_id},
        )

    # ── DELETE без параметра отклоняется ────────────────────────────

    async def test_delete_mechanic_without_setting_rejected(self):
        await self.expect_database_error(
            "DELETE FROM game_system_mechanic_versions WHERE id = :vid",
            {"vid": self.mechanic_id},
        )
        self.assertEqual(await self.count_rows(_MECH, self.mechanic_id), 1)

    async def test_delete_text_without_setting_rejected(self):
        await self.expect_database_error(
            "DELETE FROM game_system_text_versions WHERE id = :vid",
            {"vid": self.text_id},
        )

    async def test_delete_bundle_without_setting_rejected(self):
        await self.expect_database_error(
            "DELETE FROM game_system_versions WHERE id = :vid",
            {"vid": self.bundle_id},
        )

    # ── DELETE по system_id без параметра отклоняется ───────────────

    async def test_delete_by_system_without_setting_rejected(self):
        await self.expect_database_error(
            "DELETE FROM game_system_mechanic_versions WHERE system_id = :sid",
            {"sid": self.system_id},
        )

    # ── DELETE с параметром удаления системы разрешён ───────────────

    async def test_delete_with_removal_setting_allowed(self):
        async with self.sessions.begin() as session:
            await self.set_removal_setting(session, self.system_id)
            await session.execute(
                text("DELETE FROM game_system_versions WHERE id = :vid"),
                {"vid": self.bundle_id},
            )
            await session.execute(
                text("DELETE FROM game_system_text_versions WHERE id = :vid"),
                {"vid": self.text_id},
            )
            await session.execute(
                text("DELETE FROM game_system_mechanic_versions WHERE id = :vid"),
                {"vid": self.mechanic_id},
            )

        self.assertEqual(await self.count_rows(_BUNDLE, self.bundle_id), 0)
        self.assertEqual(await self.count_rows(_TEXT, self.text_id), 0)
        self.assertEqual(await self.count_rows(_MECH, self.mechanic_id), 0)

    async def test_removal_setting_does_not_protect_foreign_delete(self):
        """Параметр чужой системы не открывает удаление этой строки."""
        foreign = uuid4()

        async with self.sessions.begin() as session:
            await self.set_removal_setting(session, foreign)

            with self.assertRaises(DBAPIError) as caught:
                await session.execute(
                    text("DELETE FROM game_system_mechanic_versions WHERE id = :vid"),
                    {"vid": self.mechanic_id},
                )

        self.assertEqual(sqlstate(caught.exception), "55000")

    # ── TRUNCATE отклоняется ────────────────────────────────────────

    async def expect_truncate_guard_rejected(self, table_name):
        """Каскадный TRUNCATE доходит до гарда и получает 55000.

        Без CASCADE PostgreSQL сам отклоняет усечение таблицы, на которую
        ссылается внешний ключ (0A000), не вызывая триггер. CASCADE снимает
        это синтаксическое ограничение, и отказ обеспечивает именно гард.
        """
        await self.expect_database_error(
            f"TRUNCATE {table_name} CASCADE",
            {},
            "55000",
        )

    async def test_truncate_mechanic_versions_rejected(self):
        await self.expect_truncate_guard_rejected("game_system_mechanic_versions")
        self.assertEqual(await self.count_rows(_MECH, self.mechanic_id), 1)

    async def test_truncate_text_versions_rejected(self):
        await self.expect_truncate_guard_rejected("game_system_text_versions")
        self.assertEqual(await self.count_rows(_TEXT, self.text_id), 1)

    async def test_truncate_bundle_rejected(self):
        await self.expect_truncate_guard_rejected("game_system_versions")
        self.assertEqual(await self.count_rows(_BUNDLE, self.bundle_id), 1)

    # ── INSERT свободен (публикация возможна) ───────────────────────

    async def test_insert_mechanic_version_allowed(self):
        new_id = uuid4()

        async with self.sessions.begin() as session:
            await session.execute(
                insert(_MECH).values(
                    id=new_id,
                    system_id=self.system_id,
                    version_number=2,
                    source_draft_revision=2,
                    mechanic_json=MECHANIC_SNAPSHOT,
                    rules_engine_version="1.0",
                )
            )

        self.assertEqual(await self.count_rows(_MECH, new_id), 1)

    # ── Триггеры зарегистрированы и активны ─────────────────────────

    async def test_triggers_registered_on_all_split_tables(self):
        async with self.engine.connect() as connection:
            result = await connection.execute(
                text(
                    "SELECT c.relname, t.tgname, t.tgenabled "
                    "FROM pg_trigger AS t "
                    "JOIN pg_class AS c ON c.oid = t.tgrelid "
                    "JOIN pg_namespace AS n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = current_schema() "
                    "AND c.relname = ANY(:names) AND NOT t.tgisinternal"
                ),
                {"names": list(_TABLES)},
            )
            rows = result.all()

        enabled = {
            (relname, tgname): (mode.decode() if isinstance(mode, bytes) else mode)
            for relname, tgname, mode in rows
        }

        for table_name in _TABLES:
            self.assertEqual(
                enabled.get((table_name, f"{table_name}_immutable")),
                "O",
                f"Триггер immutable не активен на {table_name}",
            )
            self.assertEqual(
                enabled.get((table_name, f"{table_name}_no_truncate")),
                "O",
                f"Триггер no_truncate не активен на {table_name}",
            )


if __name__ == "__main__":
    unittest.main()
