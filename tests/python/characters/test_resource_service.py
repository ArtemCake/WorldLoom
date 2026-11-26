# tests/python/characters/test_resource_service.py

"""Проверки Этапа F2: хранение значений ресурсов и журнал причин (§10).

Приёмка договора (§27, этап F): нет двойного списания и переброса;
одновременные действия согласованы; независимые ресурсы не снимаются
вместе. Значения лежат в отдельной таблице, максимум вычисляет ядро,
поэтому второго источника правды нет (§30#2).
"""

from __future__ import annotations

import asyncio
import os
import unittest
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app.infrastructure.database.model_registry import configure_models

# Полная загрузка моделей разрешает строковые ссылки relationship
# до первого обращения к мапперам.
configure_models()

from backend.app.modules.characters.errors import (
	CharacterStateNotInitialized,
	InvalidCharacterStateChange,
)
from backend.app.modules.characters.models import Character, SheetResourceChange, SheetResourceValue
from backend.app.modules.characters.services import resource_service as resources
from backend.app.modules.game_systems.models.system_versions import GameSystemMechanicVersion
from backend.app.modules.game_systems.rules.mechanic_codec import profile_to_mechanic
from backend.app.modules.game_systems.schemas.game_rules import RulesProfile
from tests.python.rules.pg_support import (
	USER_INSERT_SQL,
	PostgresTestCase,
	apply_migrations,
	require_connection,
	system_values,
	user_values,
)

_VERSIONS = GameSystemMechanicVersion.__table__
_CHARACTERS = Character.__table__

# Профиль версии 4: один показатель и два ресурса.
# "mana" — фиксированный максимум, "focus" — максимум через ссылку на
# показатель, чтобы проверить вычисление максимума ядром, а не хранение.
_PROFILE = {
	"schema_version": 4,
	"calculations": {
		"attributes": {
			"constitution": {"label": "Телосложение", "min_value": 0, "max_value": 20},
		},
		"derived": {},
	},
	"initial_attributes": {"constitution": 10},
	"resources": {
		"mana": {
			"label": "Мана",
			"maximum": 10,
			"initial": "full",
			"recovery": {"short_rest": 5, "long_rest": "full"},
		},
		"focus": {
			"label": "Фокус",
			"maximum": "attribute.constitution",
			"initial": "full",
			"recovery": {"long_rest": "full"},
		},
	},
}

# Начальное состояние листа: constitution=10 → максимум focus = 10.
_STATE = {"schema_version": 1, "attributes": {"constitution": 10}}


def database_url():
	raw = os.environ.get("WORLDLOOM_RULES_TEST_URL")

	if not raw:
		raise unittest.SkipTest("Не задан WORLDLOOM_RULES_TEST_URL; проверка PostgreSQL не выполнялась")

	url = make_url(raw)

	if url.drivername != "postgresql+asyncpg":
		raise RuntimeError("Для тестов требуется подключение postgresql+asyncpg")

	if not url.database or not url.database.endswith(("_test", "_tests")):
		raise RuntimeError("Имя отдельной тестовой БД должно заканчиваться на _test или _tests")

	return url


class ResourceServicePostgreSQLTests(PostgresTestCase):

	async def asyncSetUp(self):
		url = database_url()
		await require_connection(url)

		self.url = url
		self.schema = f"wl_stagef2_{uuid4().hex}"
		self.owner_id = uuid4()
		self.engine = None
		self.profile = RulesProfile.model_validate(_PROFILE)
		self.admin_engine = create_async_engine(url, poolclass=NullPool, hide_parameters=True)
		self.addAsyncCleanup(self.cleanup_database)

		async with self.admin_engine.begin() as connection:
			await connection.execute(text(f'CREATE SCHEMA "{self.schema}"'))

		self.engine = create_async_engine(
			url,
			poolclass=NullPool,
			hide_parameters=True,
			isolation_level="READ COMMITTED",
			connect_args={"server_settings": {"search_path": self.schema, "lock_timeout": "5000", "statement_timeout": "10000"}},
		)
		self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

		async with self.engine.begin() as connection:
			await connection.run_sync(apply_migrations)
			await connection.execute(USER_INSERT_SQL, user_values(self.owner_id))

	def new_connect_args(self):
		return {
			"server_settings": {
				"search_path": self.schema,
				"lock_timeout": "5000",
				"statement_timeout": "10000",
			}
		}

	async def cleanup_database(self):
		if self.engine is not None:
			await self.engine.dispose()

		try:
			async with self.admin_engine.begin() as connection:
				await connection.execute(text(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE'))
		finally:
			await self.admin_engine.dispose()

	async def new_setup(self):
		"""Создать систему, публикацию правил и персонажа с состоянием."""
		values = system_values()

		async with self.sessions.begin() as session:
			await session.execute(
				text(
					"INSERT INTO game_systems (id, name, slug, rules_engine_version, is_active) "
					"VALUES (:id, :name, :slug, '1.0', true)"
				),
				{"id": values["id"], "name": values["name"], "slug": values["slug"]},
			)
			version_id = uuid4()
			await session.execute(
				_VERSIONS.insert().values(
					id=version_id,
					system_id=values["id"],
					version_number=1,
					source_draft_revision=1,
					mechanic_json=profile_to_mechanic(
						self.profile.model_dump(mode="json")
					),
					rules_engine_version="1.0",
				)
			)
			character_id = uuid4()
			await session.execute(
				_CHARACTERS.insert().values(
					id=character_id,
					user_id=self.owner_id,
					name=f"Персонаж {uuid4().hex[:8]}",
					revision=1,
					state_json=_STATE,
					state_rules_version_id=version_id,
				)
			)

		return character_id

	async def init(self, character_id):
		async with self.sessions.begin() as session:
			character = await session.get(Character, character_id)
			await resources.init_resources(session, character)

	async def values(self, character_id):
		async with self.sessions() as session:
			character = await session.get(Character, character_id)
			read = await resources.read_resources(session, character)

		return {item.code: (item.value, item.maximum) for item in read.items}

	async def raw_values(self, character_id):
		async with self.sessions() as session:
			rows = (
				await session.execute(
					select(SheetResourceValue.code, SheetResourceValue.value).where(
						SheetResourceValue.owner_key == character_id
					)
				)
			).all()

		return {code: value for code, value in rows}

	async def journal(self, character_id):
		async with self.sessions() as session:
			rows = (
				await session.execute(
					select(
						SheetResourceChange.code,
						SheetResourceChange.reason_type,
						SheetResourceChange.previous_value,
						SheetResourceChange.value,
						SheetResourceChange.delta,
					).where(SheetResourceChange.owner_key == character_id)
					.order_by(SheetResourceChange.created_at, SheetResourceChange.id)
				)
			).all()

		return [tuple(row) for row in rows]

	async def set_constitution(self, character_id, value):
		"""Сменить показатель так, чтобы поменялся вычисленный максимум focus."""
		async with self.sessions.begin() as session:
			await session.execute(
				text(
					"UPDATE characters SET state_json = "
					"jsonb_set(state_json, '{attributes,constitution}', to_jsonb(CAST(:v AS integer))) "
					"WHERE id = :id"
				),
				{"id": character_id, "v": value},
			)

	# ---------- §10: начальное заполнение ----------

	async def test_init_creates_values_with_computed_maximum(self):
		cid = await self.new_setup()
		await self.init(cid)

		values = await self.values(cid)
		self.assertEqual(values["mana"], (10, 10))
		# Максимум focus вычислен ядром из constitution=10, а не сохранён.
		self.assertEqual(values["focus"], (10, 10))

		journal = await self.journal(cid)
		self.assertEqual({row[1] for row in journal}, {"init"})
		self.assertEqual(len(journal), 2)

	async def test_init_is_idempotent(self):
		cid = await self.new_setup()
		await self.init(cid)
		await self.init(cid)

		# Повтор не добавляет записей и не меняет запас (§27-E).
		self.assertEqual(len(await self.journal(cid)), 2)
		self.assertEqual(await self.raw_values(cid), {"mana": 10, "focus": 10})

	async def test_spend_without_initialization_rejected(self):
		cid = await self.new_setup()

		async with self.sessions.begin() as session:
			character = await session.get(Character, cid)
			with self.assertRaises(CharacterStateNotInitialized):
				await resources.apply_resource_limits(session, character, "clamp")

	# ---------- §10 / §27-F: списание ----------

	async def test_spend_insufficient_leaves_state_unchanged(self):
		cid = await self.new_setup()
		await self.init(cid)

		async with self.sessions.begin() as session:
			character = await session.get(Character, cid)
			with self.assertRaises(InvalidCharacterStateChange):
				await resources.spend_resources(session, character, {"mana": 11})

		# Отказ ничего не списал и не записал в журнал (§27-F).
		self.assertEqual(await self.raw_values(cid), {"mana": 10, "focus": 10})
		self.assertEqual({row[1] for row in await self.journal(cid)}, {"init"})

	async def test_spend_success_records_reason(self):
		cid = await self.new_setup()
		await self.init(cid)

		async with self.sessions.begin() as session:
			character = await session.get(Character, cid)
			updated = await resources.spend_resources(
				session, character, {"mana": 3}, source_type="effect", comment="Заклинание"
			)

		self.assertEqual(updated.values["mana"], 7)
		self.assertEqual(await self.raw_values(cid), {"mana": 7, "focus": 10})

		spend_rows = [row for row in await self.journal(cid) if row[1] == "spend"]
		self.assertEqual(spend_rows, [("mana", "spend", 10, 7, -3)])

	async def test_spend_independent_resource_not_withdrawn(self):
		"""Независимый ресурс не меняется при списании другого (§27-F)."""
		cid = await self.new_setup()
		await self.init(cid)

		async with self.sessions.begin() as session:
			character = await session.get(Character, cid)
			await resources.spend_resources(session, character, {"mana": 4})

		self.assertEqual(await self.raw_values(cid), {"mana": 6, "focus": 10})
		# Журнал содержит init для обоих ресурсов, поэтому проверяем
		# что spend есть только для списанного.
		spend_rows = [row for row in await self.journal(cid) if row[1] == "spend"]
		self.assertEqual({row[0] for row in spend_rows}, {"mana"})

	# ---------- §10: восстановление ----------

	async def test_restore_clamped_to_maximum(self):
		cid = await self.new_setup()
		await self.init(cid)

		async with self.sessions.begin() as session:
			character = await session.get(Character, cid)
			await resources.spend_resources(session, character, {"mana": 8})  # mana=2

		async with self.sessions.begin() as session:
			character = await session.get(Character, cid)
			updated = await resources.restore_resources(session, character, {"mana": 99})

		# Восстановление не выходит за максимум (§10).
		self.assertEqual(updated.values["mana"], 10)
		restore_rows = [row for row in await self.journal(cid) if row[1] == "restore"]
		self.assertEqual(restore_rows, [("mana", "restore", 2, 10, 8)])

	async def test_recover_by_event(self):
		cid = await self.new_setup()
		await self.init(cid)

		async with self.sessions.begin() as session:
			character = await session.get(Character, cid)
			await resources.spend_resources(session, character, {"mana": 4})  # mana=6

		async with self.sessions.begin() as session:
			character = await session.get(Character, cid)
			updated = await resources.recover_resources(session, character, "short_rest")

		# short_rest = +5 → 6+5=11, ограничен максимумом 10.
		self.assertEqual(updated.values["mana"], 10)

		recover_rows = [row for row in await self.journal(cid) if row[1] == "recover"]
		self.assertEqual(recover_rows, [("mana", "recover", 6, 10, 4)])

	# ---------- §10: политика ограничения запаса ----------

	async def test_limit_policy_clamp(self):
		cid = await self.new_setup()
		await self.init(cid)  # focus=10, максимум focus = constitution = 10

		await self.set_constitution(cid, 5)  # максимум focus теперь 5

		async with self.sessions.begin() as session:
			character = await session.get(Character, cid)
			updated = await resources.apply_resource_limits(session, character, "clamp")

		self.assertEqual(updated.values["focus"], 5)
		limit_rows = [row for row in await self.journal(cid) if row[1] == "limit"]
		self.assertEqual(limit_rows, [("focus", "limit", 10, 5, -5)])
		# mana не тронут политикой.
		self.assertNotIn("mana", {row[0] for row in limit_rows})

	async def test_limit_policy_keep_records_overflow(self):
		cid = await self.new_setup()
		await self.init(cid)
		await self.set_constitution(cid, 5)

		async with self.sessions.begin() as session:
			character = await session.get(Character, cid)
			updated = await resources.apply_resource_limits(session, character, "keep")

		# keep сохраняет запас сверх максимума, но фиксирует переполнение.
		self.assertEqual(updated.values["focus"], 10)
		limit_rows = [row for row in await self.journal(cid) if row[1] == "limit"]
		self.assertEqual(limit_rows, [("focus", "limit", 10, 10, 0)])

	# ---------- §10: ручная правка ----------

	async def test_manual_set_within_range(self):
		cid = await self.new_setup()
		await self.init(cid)

		async with self.sessions.begin() as session:
			character = await session.get(Character, cid)
			await resources.set_resource_value(session, character, "mana", 3, comment="Правка мастера")

		self.assertEqual((await self.raw_values(cid))["mana"], 3)
		manual_rows = [row for row in await self.journal(cid) if row[1] == "manual"]
		self.assertEqual(manual_rows, [("mana", "manual", 10, 3, -7)])

	async def test_manual_set_above_maximum_rejected(self):
		cid = await self.new_setup()
		await self.init(cid)

		async with self.sessions.begin() as session:
			character = await session.get(Character, cid)
			with self.assertRaises(InvalidCharacterStateChange):
				await resources.set_resource_value(session, character, "mana", 99)

		self.assertEqual((await self.raw_values(cid))["mana"], 10)

	async def test_manual_set_unknown_resource_rejected(self):
		cid = await self.new_setup()
		await self.init(cid)

		async with self.sessions.begin() as session:
			character = await session.get(Character, cid)
			with self.assertRaises(InvalidCharacterStateChange):
				await resources.set_resource_value(session, character, "unknown", 1)

	# ---------- §27-F: одновременные действия согласованы ----------

	async def test_concurrent_spend_is_serialized(self):
		"""Два одновременных списания по одному ресурсу не тратят больше запаса."""
		cid = await self.new_setup()
		await self.init(cid)  # mana = 10

		second_engine = create_async_engine(
			self.url,
			poolclass=NullPool,
			hide_parameters=True,
			isolation_level="READ COMMITTED",
			connect_args=self.new_connect_args(),
		)
		self.addAsyncCleanup(second_engine.dispose)
		second_sessions = async_sessionmaker(second_engine, expire_on_commit=False)

		async def spend(factory):
			try:
				async with factory.begin() as session:
					character = await session.get(Character, cid)
					await resources.spend_resources(session, character, {"mana": 6})
				return "ok"
			except InvalidCharacterStateChange:
				return "rejected"

		# Каждый пытается списать 6 из 10: пройти может только один (§27-F).
		results = await asyncio.gather(spend(self.sessions), spend(second_sessions))

		self.assertEqual(sorted(results), ["ok", "rejected"])
		self.assertEqual((await self.raw_values(cid))["mana"], 4)

		spend_rows = [row for row in await self.journal(cid) if row[1] == "spend"]
		self.assertEqual(spend_rows, [("mana", "spend", 10, 4, -6)])


if __name__ == "__main__":
	unittest.main()
