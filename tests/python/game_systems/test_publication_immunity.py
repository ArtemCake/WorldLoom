# tests/python/game_systems/test_publication_immunity.py

"""Доприёмка §27-G на реальной PostgreSQL: обновление источника не меняет выпуск.

В `test_g1_publication_acceptance.py` это свойство сознательно НЕ эмулировалось
моками: подмена проверки на уровне СУБД дала бы ложное подтверждение. После
включения защиты версий (миграция `d5b2c8e14a37`, этап G1b) свойство можно
проверить честно — на реальном пути `editor_service.publish_rules_version` и
полной цепочке миграций в изолированной схеме.

Проверяются свойства выпуска (§27-G «приёмка этапа G», §28.2):
- обновление источника (черновика) не меняет уже опубликованный снимок;
- выпуск воспроизводим: сохранённый снимок равен детерминированной сборке
  черновика, а повторный выпуск берёт актуальное состояние черновика;
- опубликованная версия неизменяема в СУБД (UPDATE/DELETE → 55000), поэтому
  публикацию не изменит ни один путь записи;
- переопределения и выбор основы сохраняются в выпуске, а новая версия
  основы и деактивация основы не меняют прежнюю публикацию системы;
- выпуск атомарен: откат внешней транзакции не оставляет частичной
  публикации, конкурентный выпуск одной ревизии создаёт одну версию.

Состав комплекта (§30#4/#5) здесь не затрагивается: проверяются только уже
реализованные правила системы и уже реализованный выбор основы.
"""

from __future__ import annotations
import asyncio
import json
import os
import unittest
from uuid import uuid4
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from backend.app.infrastructure.database.model_registry import configure_models

# Полная загрузка моделей разрешает строковые ссылки relationship
# ("User", "Game", ...) до первого обращения к мапперам.
configure_models()

from backend.app.modules.game_systems import errors
from backend.app.modules.game_systems.models.system_versions import (
    GameSystemMechanicVersion,
    GameSystemVersion,
)
from backend.app.modules.game_systems.rules.mechanic_codec import profile_to_mechanic
from backend.app.modules.game_systems.schemas.game_rules import (
    GameSystemRulesDraftCreate,
    GameSystemRulesDraftUpdate,
    GameSystemRulesPublish,
    RulesProfile,
)
from backend.app.modules.game_systems.schemas.game_system_origin import GameSystemDraftEngineSet
from backend.app.modules.game_systems.services import editor_service
from tests.python.rules.pg_support import (
    USER_INSERT_SQL,
    PostgresTestCase,
    apply_migrations,
    require_connection,
    system_values,
    user_values,
)


# Публикация — это комплект; числовой снимок живёт в версии механики.
BUNDLES = GameSystemVersion.__table__
MECHANIC_VERSIONS = GameSystemMechanicVersion.__table__

# Минимальный исполняемый профиль: один исходный показатель strength.
# Начальное значение различается в двух профилях, чтобы показать, что
# публикация привязана к снимку, а не к текущему состоянию черновика.
_BASE = {
    "schema_version": 4,
    "calculations": {
        "attributes": {"strength": {"label": "Сила", "min_value": 0, "max_value": 30}},
        "derived": {},
    },
    "resources": {},
}


def _profile(strength: int) -> dict:
    return {**_BASE, "initial_attributes": {"strength": strength}}


def database_url():
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
database_url.__test__ = False


def sqlstate(error: DBAPIError):
    return getattr(error.orig, "sqlstate", None) or getattr(error.orig, "pgcode", None)


class PublicationImmunityPostgreSQLTests(PostgresTestCase):
    async def asyncSetUp(self):
        url = database_url()
        await require_connection(url)

        self.schema = f"wl_g2imm_{uuid4().hex}"
        self.owner_id = uuid4()
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
            await connection.run_sync(apply_migrations)
            await connection.execute(USER_INSERT_SQL, user_values(self.owner_id))

    async def cleanup_database(self):
        if self.engine is not None:
            await self.engine.dispose()

        try:
            async with self.admin_engine.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE'))
        finally:
            await self.admin_engine.dispose()

    async def new_system(self) -> object:
        values = system_values()

        async with self.sessions.begin() as session:
            await session.execute(
                text(
                    "INSERT INTO game_systems (id, name, slug, rules_engine_version, is_active) "
                    "VALUES (:id, :name, :slug, '1.0', true)"
                ),
                values,
            )

        return values["id"]

    async def create_draft(self, system_id, strength: int):
        data = GameSystemRulesDraftCreate(rules=RulesProfile.model_validate(_profile(strength)))

        async with self.sessions.begin() as session:
            return await editor_service.create_rules_draft(session, system_id, data)

    async def update_draft(self, system_id, strength: int, expected_revision: int):
        data = GameSystemRulesDraftUpdate(
            expected_revision=expected_revision,
            rules=RulesProfile.model_validate(_profile(strength)),
        )

        async with self.sessions.begin() as session:
            return await editor_service.update_rules_draft(session, system_id, data)

    async def publish(self, system_id, expected_revision: int):
        data = GameSystemRulesPublish(expected_revision=expected_revision)

        async with self.sessions.begin() as session:
            return await editor_service.publish_rules_version(session, system_id, data)

    async def stored_snapshot(self, version_id) -> dict:
        """Числовой снимок комплекта: версия механики, на которую он ссылается."""
        statement = (
            select(MECHANIC_VERSIONS.c.mechanic_json)
            .select_from(
                BUNDLES.join(
                    MECHANIC_VERSIONS,
                    MECHANIC_VERSIONS.c.id == BUNDLES.c.mechanic_version_id,
                )
            )
            .where(BUNDLES.c.id == version_id)
        )

        async with self.sessions() as session:
            return (await session.execute(statement)).scalar_one()

    async def version_count(self, system_id) -> int:
        statement = select(func.count()).select_from(BUNDLES).where(BUNDLES.c.system_id == system_id)

        async with self.sessions() as session:
            return (await session.execute(statement)).scalar_one()

    async def expect_database_error(self, statement, params, expected_state: str):
        with self.assertRaises(DBAPIError) as caught:
            async with self.sessions.begin() as session:
                await session.execute(text(statement), params)

        self.assertEqual(
            sqlstate(caught.exception),
            expected_state,
            f"Ожидался код {expected_state}, получен {sqlstate(caught.exception)}",
        )

    # ---------- обновление источника не меняет публикацию ----------

    async def test_editing_draft_does_not_change_published_snapshot(self):
        """Правка черновика после выпуска оставляет опубликованный снимок прежним (§27-G)."""
        system_id = await self.new_system()
        await self.create_draft(system_id, 10)
        published = await self.publish(system_id, 1)
        original = await self.stored_snapshot(published.id)

        await self.update_draft(system_id, 14, expected_revision=2)

        self.assertEqual(await self.stored_snapshot(published.id), original)
        self.assertEqual(original["initial_attributes"]["strength"], 10)
        self.assertEqual(await self.version_count(system_id), 1)

    async def test_latest_version_is_readable_after_source_edit(self):
        """Опубликованная версия читается так же, как до правки источника (§27-G)."""
        system_id = await self.new_system()
        await self.create_draft(system_id, 10)
        published = await self.publish(system_id, 1)

        async with self.sessions() as session:
            before = await editor_service.get_rules_version(session, system_id, published.id)

        await self.update_draft(system_id, 20, expected_revision=2)

        async with self.sessions() as session:
            after = await editor_service.get_rules_version(session, system_id, published.id)

        self.assertEqual(after.rules.model_dump(mode="json"), before.rules.model_dump(mode="json"))
        self.assertEqual(after.rules.initial_attributes["strength"], 10)

    # ---------- выпуск воспроизводим ----------

    async def test_published_snapshot_equals_deterministic_build(self):
        """Сохранённый снимок равен детерминированной сборке черновика (§27-G)."""
        system_id = await self.new_system()
        draft = await self.create_draft(system_id, 10)
        published = await self.publish(system_id, 1)
        # В версии механики хранится только числовая часть профиля.
        expected = profile_to_mechanic(editor_service._rules_payload(draft.rules))

        self.assertEqual(await self.stored_snapshot(published.id), expected)

    async def test_second_release_captures_current_source_state(self):
        """Повторный выпуск берёт актуальное состояние черновика, не перезаписывая первый (§27-G)."""
        system_id = await self.new_system()
        await self.create_draft(system_id, 10)
        first = await self.publish(system_id, 1)

        await self.update_draft(system_id, 18, expected_revision=2)
        second = await self.publish(system_id, 3)

        self.assertEqual(first.version_number, 1)
        self.assertEqual(second.version_number, 2)
        self.assertEqual((await self.stored_snapshot(first.id))["initial_attributes"]["strength"], 10)
        self.assertEqual((await self.stored_snapshot(second.id))["initial_attributes"]["strength"], 18)
        self.assertEqual(await self.version_count(system_id), 2)

    # ---------- публикация неизменяема в СУБД ----------

    async def test_published_version_update_rejected_by_database(self):
        """Прямой UPDATE опубликованной версии отклоняется СУБД: источник не переписывает выпуск (§27-G)."""
        system_id = await self.new_system()
        await self.create_draft(system_id, 10)
        published = await self.publish(system_id, 1)

        await self.expect_database_error(
            "UPDATE game_system_versions SET version_number = 99 WHERE id = :vid",
            {"vid": published.id},
            "55000",
        )

    async def test_published_version_delete_rejected_by_database(self):
        """Прямой DELETE опубликованной версии отклоняется СУБД вне транзакции удаления системы (§27-G)."""
        system_id = await self.new_system()
        await self.create_draft(system_id, 10)
        published = await self.publish(system_id, 1)

        await self.expect_database_error(
            "DELETE FROM game_system_versions WHERE id = :vid",
            {"vid": published.id},
            "55000",
        )
        self.assertEqual(await self.version_count(system_id), 1)

    # ---------- конфликт ревизии не теряет изменения (реальный путь) ----------

    async def test_stale_publish_revision_rejected_without_new_version(self):
        """Устаревшая ревизия отклоняется на реальном пути и не создаёт версию (§27-G)."""
        system_id = await self.new_system()
        await self.create_draft(system_id, 10)

        with self.assertRaises(errors.GameSystemRulesConflict):
            await self.publish(system_id, 2)

        self.assertEqual(await self.version_count(system_id), 0)

        published = await self.publish(system_id, 1)
        self.assertEqual(published.version_number, 1)

    # ---------- атомарность выпуска (§28.2, §17.3 п.6) ----------

    async def test_failed_outer_transaction_leaves_no_partial_publication(self):
        """Отказ внешней транзакции не оставляет частично видимой публикации (§17.3 п.6-7)."""

        class AbortPublication(Exception):
            pass

        system_id = await self.new_system()
        await self.create_draft(system_id, 10)

        # Вставка версии происходит в транзакции вызывающего слоя; её откат
        # обязан убрать и версию, и потребление ревизии черновика.
        with self.assertRaises(AbortPublication):
            async with self.sessions.begin() as session:
                await editor_service.publish_rules_version(session, system_id, GameSystemRulesPublish(expected_revision=1))
                raise AbortPublication()

        self.assertEqual(await self.version_count(system_id), 0)

        async with self.sessions() as session:
            state = await editor_service.get_rules_draft(session, system_id)

        self.assertEqual(state.draft.revision, 1)

    # ---------- конкурентные публикации (§28.2) ----------

    async def test_concurrent_publications_accept_only_one_release(self):
        """Одновременный выпуск одной ревизии создаёт ровно одну версию (§28.2)."""
        system_id = await self.new_system()
        await self.create_draft(system_id, 10)

        async def attempt():
            try:
                return await self.publish(system_id, 1)
            except errors.GameSystemRulesConflict as exc:
                return exc

        results = await asyncio.gather(attempt(), attempt())
        accepted = [item for item in results if not isinstance(item, errors.GameSystemRulesConflict)]
        conflicts = [item for item in results if isinstance(item, errors.GameSystemRulesConflict)]

        self.assertEqual(len(accepted), 1)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(await self.version_count(system_id), 1)

        async with self.sessions() as session:
            state = await editor_service.get_rules_draft(session, system_id)

        self.assertEqual(state.draft.revision, 2)

    # ---------- переопределения и выбор основы (§27-G) ----------

    async def new_engine(self, *, visibility="private", strength=10) -> object:
        """Создать движок и опубликовать его версию прямым INSERT.

        Защита версий движка запрещает UPDATE и DELETE, но не INSERT,
        поэтому публикация основы создаётся так же, как её создаёт сервис.
        """
        engine_id = uuid4()
        version_id = uuid4()
        profile = _profile(strength)

        async with self.sessions.begin() as session:
            await session.execute(
                text(
                    "INSERT INTO rule_engines (id, owner_id, name, slug, visibility, is_active) "
                    "VALUES (:id, :owner_id, :name, :slug, :visibility, true)"
                ),
                {
                    "id": engine_id,
                    "owner_id": self.owner_id,
                    "name": f"Основа {engine_id.hex[:8]}",
                    "slug": f"engine-{engine_id}",
                    "visibility": visibility,
                },
            )
            await session.execute(
                text(
                    "INSERT INTO rule_engine_versions "
                    "(id, engine_id, version_number, source_draft_revision, rules_json, rules_engine_version) "
                    "VALUES (:id, :engine_id, 1, 1, CAST(:rules AS jsonb), '1.0')"
                ),
                {"id": version_id, "engine_id": engine_id, "rules": json.dumps(profile)},
            )

        return engine_id, version_id

    async def choose_origin(self, system_id, engine_id, version_id, overrides, *, expected_revision=None):
        data = GameSystemDraftEngineSet(
            engine_id=engine_id,
            engine_version_id=version_id,
            rules_overrides=overrides,
            expected_revision=expected_revision,
        )

        async with self.sessions.begin() as session:
            return await editor_service.set_rules_draft_engine(session, system_id, self.owner_id, data)

    async def version_row(self, version_id) -> dict:
        """Прочитать номер версии комплекта и поля версии механики."""
        statement = (
            select(
                BUNDLES.c.version_number,
                MECHANIC_VERSIONS.c.engine_version_id,
                MECHANIC_VERSIONS.c.mechanic_overrides_json,
                MECHANIC_VERSIONS.c.mechanic_json,
            )
            .select_from(
                MECHANIC_VERSIONS.join(
                    BUNDLES,
                    BUNDLES.c.mechanic_version_id == MECHANIC_VERSIONS.c.id,
                )
            )
            .where(BUNDLES.c.id == version_id)
        )

        async with self.sessions() as session:
            return dict((await session.execute(statement)).mappings().one())

    async def test_linked_draft_publishes_origin_and_overrides(self):
        """Публикация связанного черновика сохраняет основу и переопределения (§27-G)."""
        system_id = await self.new_system()
        engine_id, version_id = await self.new_engine(strength=10)

        await self.choose_origin(
            system_id,
            engine_id,
            version_id,
            {"initial_attributes": {"strength": 18}},
            expected_revision=None,
        )
        published = await self.publish(system_id, 1)
        row = await self.version_row(published.id)

        self.assertEqual(row["engine_version_id"], version_id)
        self.assertEqual(row["mechanic_json"]["initial_attributes"]["strength"], 18)
        self.assertEqual(row["mechanic_overrides_json"], {"initial_attributes": {"strength": 18}})

    async def test_new_engine_release_does_not_change_published_system_version(self):
        """Новая версия основы не меняет уже выпущенную публикацию системы (§27-G)."""
        system_id = await self.new_system()
        engine_id, first_version = await self.new_engine(strength=10)

        await self.choose_origin(
            system_id, engine_id, first_version, {"initial_attributes": {"strength": 12}}, expected_revision=None
        )
        published = await self.publish(system_id, 1)
        original = await self.version_row(published.id)

        # Выпускаем вторую версию той же основы прямым INSERT, как это делает сервис движка.
        second_version = uuid4()

        async with self.sessions.begin() as session:
            await session.execute(
                text(
                    "INSERT INTO rule_engine_versions "
                    "(id, engine_id, version_number, source_draft_revision, rules_json, rules_engine_version) "
                    "VALUES (:id, :engine_id, 2, 2, CAST(:rules AS jsonb), '1.0')"
                ),
                {"id": second_version, "engine_id": engine_id, "rules": json.dumps(_profile(25))},
            )

        after = await self.version_row(published.id)

        self.assertEqual(after, original)
        self.assertEqual(after["engine_version_id"], first_version)
        self.assertEqual(after["mechanic_json"]["initial_attributes"]["strength"], 12)

    async def test_deactivated_origin_keeps_published_system_version_readable(self):
        """Деактивация основы не меняет и не скрывает выпущенную публикацию системы (§27-G)."""
        system_id = await self.new_system()
        engine_id, version_id = await self.new_engine(strength=10)

        await self.choose_origin(
            system_id, engine_id, version_id, {"initial_attributes": {"strength": 14}}, expected_revision=None
        )
        published = await self.publish(system_id, 1)
        # Числовой снимок хранится в версии механики.
        original = await self.stored_snapshot(published.id)

        async with self.sessions.begin() as session:
            await session.execute(text("UPDATE rule_engines SET is_active = false WHERE id = :id"), {"id": engine_id})

        async with self.sessions() as session:
            read = await editor_service.get_rules_version(session, system_id, published.id)
            # profile_to_mechanic от полного профиля даст ту же числовую часть.
            original_mech = profile_to_mechanic(original)
            read_mech = profile_to_mechanic(read.rules.model_dump(mode="json"))

        self.assertEqual(read_mech, original_mech)
        self.assertEqual(read.rules.initial_attributes["strength"], 14)

    async def test_mismatched_saved_snapshot_is_rejected_before_release(self):
        """Несогласованный снимок черновика отклоняется до создания версии (§17.3 п.4)."""
        system_id = await self.new_system()
        engine_id, version_id = await self.new_engine(strength=10)

        await self.choose_origin(
            system_id, engine_id, version_id, {"initial_attributes": {"strength": 12}}, expected_revision=None
        )

        # Черновик правят мимо сервиса: основа и переопределения остаются,
        # а собранный профиль перестает им соответствовать. Правка идёт
        # в числовую часть черновика механики.
        tampered = profile_to_mechanic(_profile(29))

        async with self.sessions.begin() as session:
            await session.execute(
                text("UPDATE game_system_mechanic_drafts SET mechanic_json = CAST(:rules AS jsonb) "
                     "WHERE system_id = :system_id"),
                {"rules": json.dumps(tampered), "system_id": system_id},
            )

        with self.assertRaises(errors.GameSystemRulesConflict):
            await self.publish(system_id, 1)

        self.assertEqual(await self.version_count(system_id), 0)

    async def test_foreign_engine_version_cannot_be_chosen(self):
        """Чужая закрытая основа недоступна выбору и не меняет черновик (§29, §28.3)."""
        system_id = await self.new_system()
        foreign_owner = uuid4()
        engine_id = uuid4()
        foreign_version = uuid4()

        async with self.sessions.begin() as session:
            await session.execute(USER_INSERT_SQL, user_values(foreign_owner))
            await session.execute(
                text(
                    "INSERT INTO rule_engines (id, owner_id, name, slug, visibility, is_active) "
                    "VALUES (:id, :owner_id, :name, :slug, 'private', true)"
                ),
                {
                    "id": engine_id,
                    "owner_id": foreign_owner,
                    "name": f"Чужая {engine_id.hex[:8]}",
                    "slug": f"foreign-{engine_id}",
                },
            )
            # Публикация существует и принадлежит другому владельцу:
            # отказ должен дать проверка прав, а не отсутствие строки.
            await session.execute(
                text(
                    "INSERT INTO rule_engine_versions "
                    "(id, engine_id, version_number, source_draft_revision, rules_json, rules_engine_version) "
                    "VALUES (:id, :engine_id, 1, 1, CAST(:rules AS jsonb), '1.0')"
                ),
                {"id": foreign_version, "engine_id": engine_id, "rules": json.dumps(_profile(10))},
            )

        with self.assertRaises(errors.GameSystemNotFound):
            await self.choose_origin(system_id, engine_id, foreign_version, {}, expected_revision=None)

        self.assertEqual(await self.version_count(system_id), 0)

        async with self.sessions() as session:
            state = await editor_service.get_rules_draft(session, system_id)

        self.assertIsNone(state.draft)


if __name__ == "__main__":
    unittest.main()
