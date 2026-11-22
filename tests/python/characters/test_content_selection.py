# tests/python/characters/test_content_selection.py

"""Проверки Этапа E: выборы контента и происхождение выданных свойств.

Приёмка договора (§27, этап E): повтор сохранения не дублирует выдачу;
недопустимые выборы не принимаются; классовая модель не навязывается.
"""

from __future__ import annotations

import os
import unittest
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app.infrastructure.database.model_registry import configure_models

# Полная загрузка моделей разрешает строковые ссылки relationship
# ("User", "Game", ...) до первого обращения к мапперам.
configure_models()

from backend.app.modules.catalog.models.character_building import Race
from backend.app.modules.characters.errors import (
	CharacterNotFound,
	CharacterStateConflict,
	InvalidCharacterStateChange,
)
from backend.app.modules.characters.models import (
	Character,
	CharacterContentSelection,
	SheetAttributeProvenance,
)
from backend.app.modules.characters.schemas.selection_schemas import (
	ContentGrantIn,
	ContentSelectionIn,
)
from backend.app.modules.characters.services import content_selection_service as selections
from backend.app.modules.game_systems.schemas.game_rules import RulesProfile, SheetState
from tests.python.rules.pg_support import (
	USER_INSERT_SQL,
	PostgresTestCase,
	apply_migrations,
	require_connection,
	system_values,
	user_values,
)

# Минимальный профиль: один исходный показатель strength.
# Выдача контента проверяется именно им, поэтому классы и расы
# в профиле не участвуют — это и есть «не навязывать классовую модель».
_PROFILE = {
	"schema_version": 4,
	"calculations": {
		"attributes": {
			"strength": {
				"label": "Сила",
				"min_value": 0,
				"max_value": 30,
			},
			"size": {
				"label": "Размер",
				"min_value": 0,
				"max_value": 10,
			},
		},
		"derived": {},
	},
	"initial_attributes": {"strength": 10, "size": 2},
	"resources": {},
}


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


class ContentSelectionPostgreSQLTests(PostgresTestCase):

	async def asyncSetUp(self):
		url = database_url()
		await require_connection(url)

		self.schema = f"wl_stagee_{uuid4().hex}"
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

	async def cleanup_database(self):
		if self.engine is not None:
			await self.engine.dispose()

		try:
			async with self.admin_engine.begin() as connection:
				await connection.execute(text(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE'))
		finally:
			await self.admin_engine.dispose()

	async def new_system(self, *, active=True):
		values = system_values(active=active)

		async with self.sessions.begin() as session:
			await session.execute(
				text(
					"INSERT INTO game_systems (id, name, slug, rules_engine_version, is_active) "
					"VALUES (:id, :name, :slug, '1.0', :is_active)"
				),
				{"id": values["id"], "name": values["name"], "slug": values["slug"], "is_active": active},
			)

		return values["id"]

	async def new_race(self, system_id, *, name="Раса", active=True):
		race_id = uuid4()

		async with self.sessions.begin() as session:
			await session.execute(
				text(
					"INSERT INTO races (id, system_id, name, slug, speed, is_homebrew, visibility_scope, is_active) "
					"VALUES (:id, :system_id, :name, :slug, 30, false, 'private', :is_active)"
				),
				{
					"id": race_id,
					"system_id": system_id,
					"name": name,
					"slug": f"race-{race_id}",
					"is_active": active,
				},
			)

		return race_id

	async def new_character(self):
		character_id = uuid4()

		async with self.sessions.begin() as session:
			await session.execute(
				text(
					"INSERT INTO characters (id, user_id, name, revision, created_at, updated_at) "
					"VALUES (:id, :user_id, :name, 1, now(), now())"
				),
				{"id": character_id, "user_id": self.owner_id, "name": f"Персонаж {uuid4().hex[:8]}"},
			)

		return character_id

	async def get_character(self, character_id):
		async with self.sessions() as session:
			return await session.get(Character, character_id)

	async def provenance_rows(self):
		async with self.sessions() as session:
			rows = (
				await session.execute(
					select(SheetAttributeProvenance.code, SheetAttributeProvenance.source_type, SheetAttributeProvenance.amount)
				)
			).all()

		return sorted(rows)

	# ---------- §9: повтор сохранения не дублирует выдачу ----------

	async def test_repeated_apply_does_not_duplicate_grant(self):
		system_id = await self.new_system()
		character_id = await self.new_character()
		race_id = await self.new_race(system_id)
		character = await self.get_character(character_id)

		grants = [ContentGrantIn(code="strength", source_type="race", source_id=race_id, mode="add", amount=2)]
		base_state = SheetState(attributes={"strength": 10, "size": 2})

		async with self.sessions.begin() as session:
			character = await session.get(Character, character_id)
			first = await selections.apply_content_grants(
				session, character, self.profile, base_state, "race", race_id, grants
			)

		self.assertEqual(first.attributes["strength"], 12)

		# Повторное сохранение того же источника выдаёт то же значение.
		async with self.sessions.begin() as session:
			character = await session.get(Character, character_id)
			current = await session.execute(
				text("SELECT 1")
			) and SheetState(attributes={"strength": 12, "size": 2})
			repeat = await selections.apply_content_grants(
				session, character, self.profile, current, "race", race_id, grants
			)

		self.assertEqual(repeat.attributes["strength"], 12)
		self.assertEqual(len(await self.provenance_rows()), 1)

	async def test_reapplying_changed_grant_replaces_value(self):
		"""Изменение величины источника заменяет выдачу, а не складывает её."""
		system_id = await self.new_system()
		character_id = await self.new_character()
		race_id = await self.new_race(system_id)

		base_state = SheetState(attributes={"strength": 10, "size": 2})

		async with self.sessions.begin() as session:
			character = await session.get(Character, character_id)
			await selections.apply_content_grants(
				session,
				character,
				self.profile,
				base_state,
				"race",
				race_id,
				[ContentGrantIn(code="strength", source_type="race", source_id=race_id, mode="add", amount=2)],
			)

		current = SheetState(attributes={"strength": 12, "size": 2})

		async with self.sessions.begin() as session:
			character = await session.get(Character, character_id)
			updated = await selections.apply_content_grants(
				session,
				character,
				self.profile,
				current,
				"race",
				race_id,
				[ContentGrantIn(code="strength", source_type="race", source_id=race_id, mode="add", amount=5)],
			)

		# Снято +2, наложено +5: 10 + 5, а не 12 + 5.
		self.assertEqual(updated.attributes["strength"], 15)
		self.assertEqual(len(await self.provenance_rows()), 1)

	# ---------- §13: отзыв снимает только свой источник ----------

	async def test_withdraw_keeps_other_source_value(self):
		"""Одноимённое свойство другого источника остаётся."""
		system_id = await self.new_system()
		character_id = await self.new_character()
		race_id = await self.new_race(system_id)
		feat_id = uuid4()

		async with self.sessions.begin() as session:
			character = await session.get(Character, character_id)
			state = SheetState(attributes={"strength": 10, "size": 2})
			state = await selections.apply_content_grants(
				session,
				character,
				self.profile,
				state,
				"race",
				race_id,
				[ContentGrantIn(code="strength", source_type="race", source_id=race_id, mode="add", amount=2)],
			)
			state = await selections.apply_content_grants(
				session,
				character,
				self.profile,
				state,
				"feat",
				feat_id,
				[ContentGrantIn(code="strength", source_type="feat", source_id=feat_id, mode="add", amount=1)],
			)

		self.assertEqual(state.attributes["strength"], 13)

		async with self.sessions.begin() as session:
			character = await session.get(Character, character_id)
			withdrawn = await selections.withdraw_source_grants(
				session, character, self.profile, state, "race", race_id
			)

		# Осталась только выдача черты.
		self.assertEqual(withdrawn.attributes["strength"], 11)
		self.assertEqual(await self.provenance_rows(), [("strength", "feat", 1)])

	async def test_withdraw_missing_source_changes_nothing(self):
		system_id = await self.new_system()
		character_id = await self.new_character()
		state = SheetState(attributes={"strength": 10, "size": 2})

		async with self.sessions.begin() as session:
			character = await session.get(Character, character_id)
			result = await selections.withdraw_source_grants(
				session, character, self.profile, state, "race", uuid4()
			)

		self.assertEqual(result.attributes, state.attributes)

	# ---------- §9: недопустимые выборы не принимаются ----------

	async def test_grant_out_of_range_is_rejected(self):
		"""Ядро отклоняет выдачу за границами показателя; состояние не меняется."""
		system_id = await self.new_system()
		character_id = await self.new_character()
		race_id = await self.new_race(system_id)

		async with self.sessions.begin() as session:
			character = await session.get(Character, character_id)
			with self.assertRaises(InvalidCharacterStateChange):
				await selections.apply_content_grants(
					session,
					character,
					self.profile,
					SheetState(attributes={"strength": 10, "size": 2}),
					"race",
					race_id,
					[ContentGrantIn(code="strength", source_type="race", source_id=race_id, mode="add", amount=99)],
				)

		self.assertEqual(await self.provenance_rows(), [])

	async def test_grant_unknown_code_is_rejected(self):
		system_id = await self.new_system()
		character_id = await self.new_character()
		race_id = await self.new_race(system_id)

		async with self.sessions.begin() as session:
			character = await session.get(Character, character_id)
			with self.assertRaises(InvalidCharacterStateChange):
				await selections.apply_content_grants(
					session,
					character,
					self.profile,
					SheetState(attributes={"strength": 10, "size": 2}),
					"race",
					race_id,
					[ContentGrantIn(code="fly_speed", source_type="race", source_id=race_id, mode="add", amount=1)],
				)

	async def test_grant_source_mismatch_is_rejected(self):
		system_id = await self.new_system()
		character_id = await self.new_character()
		race_id = await self.new_race(system_id)

		async with self.sessions.begin() as session:
			character = await session.get(Character, character_id)
			with self.assertRaises(InvalidCharacterStateChange):
				await selections.apply_content_grants(
					session,
					character,
					self.profile,
					SheetState(attributes={"strength": 10, "size": 2}),
					"race",
					race_id,
					[ContentGrantIn(code="strength", source_type="feat", source_id=race_id, mode="add", amount=1)],
				)

	# ---------- §9: выбор элемента каталога ----------

	async def test_select_content_requires_existing_entry(self):
		system_id = await self.new_system()
		character_id = await self.new_character()

		async with self.sessions.begin() as session:
			character = await session.get(Character, character_id)
			with self.assertRaises(CharacterNotFound):
				await selections.select_content(
					session, character, system_id, ContentSelectionIn(source_type="race", source_id=uuid4())
				)

	async def test_select_content_rejects_entry_of_other_system(self):
		system_id = await self.new_system()
		other_system_id = await self.new_system()
		character_id = await self.new_character()
		race_id = await self.new_race(other_system_id)

		async with self.sessions.begin() as session:
			character = await session.get(Character, character_id)
			with self.assertRaises(CharacterNotFound):
				await selections.select_content(
					session, character, system_id, ContentSelectionIn(source_type="race", source_id=race_id)
				)

	async def test_select_content_rejects_inactive_entry(self):
		system_id = await self.new_system()
		character_id = await self.new_character()
		race_id = await self.new_race(system_id, active=False)

		async with self.sessions.begin() as session:
			character = await session.get(Character, character_id)
			with self.assertRaises(CharacterNotFound):
				await selections.select_content(
					session, character, system_id, ContentSelectionIn(source_type="race", source_id=race_id)
				)

	async def test_select_same_source_twice_is_idempotent(self):
		"""Повтор того же выбора не создаёт вторую запись (§9)."""
		system_id = await self.new_system()
		character_id = await self.new_character()
		race_id = await self.new_race(system_id)

		for _ in range(2):
			async with self.sessions.begin() as session:
				character = await session.get(Character, character_id)
				await selections.select_content(
					session, character, system_id, ContentSelectionIn(source_type="race", source_id=race_id)
				)

		async with self.sessions() as session:
			rows = (await session.execute(select(CharacterContentSelection))).scalars().all()

		self.assertEqual(len(rows), 1)
		self.assertTrue(rows[0].is_active)

	async def test_select_different_source_of_same_type_requires_deselect(self):
		system_id = await self.new_system()
		character_id = await self.new_character()
		first_race = await self.new_race(system_id, name="Первая")
		second_race = await self.new_race(system_id, name="Вторая")

		async with self.sessions.begin() as session:
			character = await session.get(Character, character_id)
			await selections.select_content(
				session, character, system_id, ContentSelectionIn(source_type="race", source_id=first_race)
			)

		async with self.sessions.begin() as session:
			character = await session.get(Character, character_id)
			with self.assertRaises(CharacterStateConflict):
				await selections.select_content(
					session, character, system_id, ContentSelectionIn(source_type="race", source_id=second_race)
				)

		# После отмены новый выбор принимается.
		async with self.sessions.begin() as session:
			character = await session.get(Character, character_id)
			await selections.deselect_content(session, character, "race")

		async with self.sessions.begin() as session:
			character = await session.get(Character, character_id)
			selection = await selections.select_content(
				session, character, system_id, ContentSelectionIn(source_type="race", source_id=second_race)
			)

		self.assertEqual(selection.source_id, second_race)

	async def test_select_unknown_source_type_is_rejected(self):
		"""Неизвестная категория не превращается в скрытый выбор (§13)."""
		system_id = await self.new_system()
		character_id = await self.new_character()

		async with self.sessions.begin() as session:
			character = await session.get(Character, character_id)
			with self.assertRaises(InvalidCharacterStateChange):
				await selections.select_content(
					session, character, system_id, ContentSelectionIn(source_type="artifact_slot", source_id=uuid4())
				)

	# ---------- §14.1: происхождение читается ----------

	async def test_list_provenance_reports_source(self):
		system_id = await self.new_system()
		character_id = await self.new_character()
		race_id = await self.new_race(system_id)

		async with self.sessions.begin() as session:
			character = await session.get(Character, character_id)
			await selections.apply_content_grants(
				session,
				character,
				self.profile,
				SheetState(attributes={"strength": 10, "size": 2}),
				"race",
				race_id,
				[ContentGrantIn(code="size", source_type="race", source_id=race_id, mode="set", amount=4)],
			)

		async with self.sessions() as session:
			character = await session.get(Character, character_id)
			records = await selections.list_provenance(session, character)

		self.assertEqual(len(records), 1)
		self.assertEqual(records[0].code, "size")
		self.assertEqual(records[0].source_type, "race")
		self.assertEqual(records[0].source_id, race_id)
		self.assertEqual(records[0].mode, "set")

	async def test_owner_constraint_requires_single_owner(self):
		"""Происхождение принадлежит либо шаблону, либо листу (§14.1)."""
		async with self.sessions.begin() as session:
			with self.assertRaises(Exception):
				await session.execute(
					text(
						"INSERT INTO sheet_attribute_provenance "
						"(id, character_sheet_id, character_id, code, source_type, mode, amount, previous_value) "
						"VALUES (:id, :sheet, :char, 'strength', 'race', 'add', 1, 0)"
					),
					{"id": uuid4(), "sheet": uuid4(), "char": uuid4()},
				)


if __name__ == "__main__":
	unittest.main()
