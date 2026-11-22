# tests/python/characters/test_effect_service.py

"""Проверки Этапа F3: экземпляры эффектов на цели и журнал причин (§12).

Приёмка договора (§27, этап F): независимые эффекты не снимаются
вместе; одновременные действия согласованы. Дополнительно §12:
повтор обработки одного события не создаёт копию экземпляра и не
снимает эффект дважды; удаление одного экземпляра не снимает другой
только из-за совпадения названия; порядок загрузки не определяет
результат свёртки.
"""

from __future__ import annotations

import os
import unittest
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app.infrastructure.database.model_registry import configure_models

# Полная загрузка моделей разрешает строковые ссылки relationship
# до первого обращения к мапперам.
configure_models()

from backend.app.modules.characters.errors import (
	CharacterNotFound,
	InvalidCharacterStateChange,
)
from backend.app.modules.characters.models import Character, EffectChange, EffectInstance
from backend.app.modules.characters.schemas.effect_schemas import (
	EffectExtendIn,
	EffectInstanceApplyIn,
	EffectModifierIn,
)
from backend.app.modules.characters.services import effect_service as effects
from tests.python.rules.pg_support import (
	USER_INSERT_SQL,
	PostgresTestCase,
	apply_migrations,
	require_connection,
	user_values,
)

_CHARACTERS = Character.__table__


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


def mod(code, value, stacking="stacking", priority=0):
	return EffectModifierIn(code=code, value=value, stacking=stacking, priority=priority)


class EffectServicePostgreSQLTests(PostgresTestCase):

	async def asyncSetUp(self):
		url = database_url()
		await require_connection(url)

		self.schema = f"wl_stagef3_{uuid4().hex}"
		self.owner_id = uuid4()
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

	async def cleanup_database(self):
		if self.engine is not None:
			await self.engine.dispose()

		try:
			async with self.admin_engine.begin() as connection:
				await connection.execute(text(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE'))
		finally:
			await self.admin_engine.dispose()

	async def new_target(self):
		"""Создать персонажа-цель. Эффектам не нужна публикация правил."""
		character_id = uuid4()

		async with self.sessions.begin() as session:
			await session.execute(
				_CHARACTERS.insert().values(
					id=character_id,
					user_id=self.owner_id,
					name=f"Цель {uuid4().hex[:8]}",
					revision=1,
				)
			)

		return character_id

	async def get_target(self, character_id):
		async with self.sessions() as session:
			return await session.get(Character, character_id)

	async def apply(self, character_id, **kwargs):
		async with self.sessions.begin() as session:
			character = await session.get(Character, character_id)
			return await effects.apply_effect(session, character, EffectInstanceApplyIn(**kwargs))

	async def call(self, func, character_id, *args, **kwargs):
		async with self.sessions.begin() as session:
			character = await session.get(Character, character_id)
			return await func(session, character, *args, **kwargs)

	async def statuses(self, character_id):
		async with self.sessions() as session:
			rows = (
				await session.execute(
					select(EffectInstance.id, EffectInstance.status).where(
						EffectInstance.owner_key == character_id
					)
				)
			).all()

		return {str(id_): status for id_, status in rows}

	async def counts(self, character_id):
		async with self.sessions() as session:
			instances = await session.scalar(
				select(EffectInstance.id).where(EffectInstance.owner_key == character_id)
			)
			instance_count = len(
				(
					await session.execute(
						select(EffectInstance.id).where(EffectInstance.owner_key == character_id)
					)
				).all()
			)
			change_count = len(
				(
					await session.execute(
						select(EffectChange.id).where(EffectChange.owner_key == character_id)
					)
				).all()
			)

		return instance_count, change_count

	async def journal(self, character_id):
		async with self.sessions() as session:
			rows = (
				await session.execute(
					select(EffectChange.instance_id, EffectChange.reason_type, EffectChange.status_after).where(
						EffectChange.owner_key == character_id
					)
					.order_by(EffectChange.created_at, EffectChange.id)
				)
			).all()

		return [(str(instance_id), reason, after) for instance_id, reason, after in rows]

	async def aggregate(self, character_id):
		async with self.sessions() as session:
			character = await session.get(Character, character_id)
			agg = await effects.aggregate_effects(session, character)

		return {item.code: item for item in agg.items}

	# ---------- §12: экземпляр и журнал наложения ----------

	async def test_apply_creates_instance_and_journal(self):
		cid = await self.new_target()
		created = await self.apply(
			cid,
			source_type="effect",
			modifiers=[mod("strength", 2)],
			started_event="battle_start",
		)

		self.assertEqual(created.status, "active")
		self.assertIsNotNone(created.started_at)

		instances, changes = await self.counts(cid)
		self.assertEqual((instances, changes), (1, 1))
		self.assertEqual(await self.journal(cid), [(str(created.id), "apply", "active")])

	async def test_apply_rejects_unknown_stacking(self):
		"""Неизвестное правило сочетания не принимается контрактом (§12).

		Контракт отсекает ввод раньше сервиса, поэтому запись не
		создаётся ни в экземплярах, ни в журнале.
		"""
		cid = await self.new_target()

		with self.assertRaises(ValidationError):
			await self.apply(
				cid,
				source_type="effect",
				modifiers=[{"code": "strength", "value": 2, "stacking": "multiply"}],
			)

		self.assertEqual(await self.counts(cid), (0, 0))

	async def test_apply_rejects_duplicate_code_in_one_instance(self):
		cid = await self.new_target()

		with self.assertRaises(InvalidCharacterStateChange):
			await self.apply(
				cid,
				source_type="effect",
				modifiers=[mod("strength", 2), mod("strength", 3)],
			)

		self.assertEqual(await self.counts(cid), (0, 0))

	# ---------- §12: повтор события не создаёт копию ----------

	async def test_repeated_application_key_does_not_duplicate(self):
		cid = await self.new_target()
		key = uuid4()

		first = await self.apply(
			cid, source_type="effect", application_key=str(key), modifiers=[mod("strength", 2)]
		)
		second = await self.apply(
			cid, source_type="effect", application_key=str(key), modifiers=[mod("strength", 2)]
		)

		self.assertEqual(first.id, second.id)
		# Один экземпляр и одна причина наложения, несмотря на два вызова.
		self.assertEqual(await self.counts(cid), (1, 1))

	# ---------- §12: свёртка и независимость экземпляров ----------

	async def test_stacking_sums_independent_instances(self):
		cid = await self.new_target()
		await self.apply(cid, source_type="effect", source_id=str(uuid4()), modifiers=[mod("strength", 2)])
		await self.apply(cid, source_type="effect", source_id=str(uuid4()), modifiers=[mod("strength", 3)])

		agg = await self.aggregate(cid)
		self.assertEqual(agg["strength"].total, 5)
		self.assertEqual({o.result for o in agg["strength"].outcomes}, {"applied"})

	async def test_override_suppresses_others(self):
		cid = await self.new_target()
		blessing = await self.apply(
			cid, source_type="effect", source_id=str(uuid4()), modifiers=[mod("armor", 5, "stacking")]
		)
		curse = await self.apply(
			cid, source_type="effect", source_id=str(uuid4()), modifiers=[mod("armor", -2, "override")]
		)

		agg = await self.aggregate(cid)
		self.assertEqual(agg["armor"].total, -2)

		results = {str(o.instance_id): o.result for o in agg["armor"].outcomes}
		self.assertEqual(results[str(curse.id)], "applied")
		self.assertEqual(results[str(blessing.id)], "suppressed")

	async def test_highest_rule_picks_max(self):
		cid = await self.new_target()
		await self.apply(cid, source_type="effect", source_id=str(uuid4()), modifiers=[mod("ac", 1, "highest")])
		await self.apply(cid, source_type="effect", source_id=str(uuid4()), modifiers=[mod("ac", 4, "highest")])

		agg = await self.aggregate(cid)
		self.assertEqual(agg["ac"].total, 4)

	# ---------- §12: снятие одного не снимает другой ----------

	async def test_withdraw_one_keeps_same_named_other(self):
		"""Два экземпляра с одинаковым кодом: снятие одного оставляет другой (§12)."""
		cid = await self.new_target()
		first = await self.apply(cid, source_type="effect", source_id=str(uuid4()), modifiers=[mod("strength", 2)])
		await self.apply(cid, source_type="effect", source_id=str(uuid4()), modifiers=[mod("strength", 3)])

		await self.call(effects.withdraw_effect, cid, first.id, "dispel")

		statuses = await self.statuses(cid)
		self.assertEqual(statuses[str(first.id)], "withdrawn")
		self.assertEqual([s for i, s in statuses.items() if i != str(first.id)], ["active"])

		agg = await self.aggregate(cid)
		self.assertEqual(agg["strength"].total, 3)
		self.assertEqual(len(agg["strength"].outcomes), 1)

	# ---------- §12: подавление и возобновление ----------

	async def test_suppress_removes_from_aggregate_then_resume(self):
		cid = await self.new_target()
		inst = await self.apply(cid, source_type="effect", source_id=str(uuid4()), modifiers=[mod("speed", 10)])

		await self.call(effects.suppress_effect, cid, inst.id, "stunned")
		self.assertEqual((await self.aggregate(cid)).get("speed"), None)

		await self.call(effects.resume_effect, cid, inst.id, "not_stunned")
		self.assertEqual((await self.aggregate(cid))["speed"].total, 10)

		reasons = [row[1] for row in await self.journal(cid)]
		self.assertEqual(reasons, ["apply", "suppress", "apply"])

	async def test_suppress_is_idempotent(self):
		cid = await self.new_target()
		inst = await self.apply(cid, source_type="effect", source_id=str(uuid4()), modifiers=[mod("speed", 10)])

		await self.call(effects.suppress_effect, cid, inst.id, "stunned")
		await self.call(effects.suppress_effect, cid, inst.id, "stunned")

		# Повторное подавление не добавляет причину (§12).
		self.assertEqual([row[1] for row in await self.journal(cid)], ["apply", "suppress"])

	# ---------- §12: снятие по источнику и по событию ----------

	async def test_withdraw_by_source_only_that_source(self):
		cid = await self.new_target()
		src_a, src_b = uuid4(), uuid4()

		await self.apply(cid, source_type="effect", source_id=str(src_a), modifiers=[mod("strength", 2)])
		await self.apply(cid, source_type="effect", source_id=str(src_a), modifiers=[mod("dexterity", 1)])
		await self.apply(cid, source_type="effect", source_id=str(src_b), modifiers=[mod("strength", 5)])

		removed = await self.call(effects.withdraw_by_source, cid, "effect", src_a, "source_gone")
		self.assertEqual(len(removed), 2)

		agg = await self.aggregate(cid)
		# Остался только эффект источника B.
		self.assertEqual(agg["strength"].total, 5)
		self.assertNotIn("dexterity", agg)

	async def test_withdraw_by_event_only_listed_end_events(self):
		cid = await self.new_target()
		ends_on_rest = await self.apply(
			cid, source_type="effect", source_id=str(uuid4()), modifiers=[mod("mana", -2)],
			end_events=["long_rest"],
		)
		await self.apply(
			cid, source_type="effect", source_id=str(uuid4()), modifiers=[mod("hp", -1)],
			end_events=["short_rest"],
		)

		removed = await self.call(effects.withdraw_by_event, cid, "long_rest")
		self.assertEqual([str(r.id) for r in removed], [str(ends_on_rest.id)])

		statuses = await self.statuses(cid)
		self.assertEqual(statuses[str(ends_on_rest.id)], "withdrawn")
		self.assertEqual(len([s for s in statuses.values() if s == "active"]), 1)

	async def test_withdraw_is_idempotent(self):
		cid = await self.new_target()
		inst = await self.apply(cid, source_type="effect", source_id=str(uuid4()), modifiers=[mod("strength", 2)])

		await self.call(effects.withdraw_effect, cid, inst.id, "dispel")
		await self.call(effects.withdraw_effect, cid, inst.id, "dispel")

		self.assertEqual([row[1] for row in await self.journal(cid)], ["apply", "withdraw"])

	# ---------- §12: продление длительности ----------

	async def test_extend_increases_duration(self):
		cid = await self.new_target()
		inst = await self.apply(
			cid, source_type="effect", source_id=str(uuid4()), modifiers=[mod("strength", 2)],
			duration_value=3, duration_unit="turn",
		)

		extended = await self.call(
			effects.extend_effect, cid, inst.id, EffectExtendIn(duration_delta=2)
		)
		self.assertEqual(extended.duration_value, 5)
		self.assertEqual([row[1] for row in await self.journal(cid)], ["apply", "extend"])

	async def test_extend_without_duration_rejected(self):
		cid = await self.new_target()
		inst = await self.apply(cid, source_type="effect", source_id=str(uuid4()), modifiers=[mod("strength", 2)])

		with self.assertRaises(InvalidCharacterStateChange):
			await self.call(effects.extend_effect, cid, inst.id, EffectExtendIn(duration_delta=1))

	# ---------- §12: снятый экземпляр не продлевается и не подавляется ----------

	async def test_withdrawn_instance_rejects_suppress_and_extend(self):
		cid = await self.new_target()
		inst = await self.apply(
			cid, source_type="effect", source_id=str(uuid4()), modifiers=[mod("strength", 2)],
			duration_value=3, duration_unit="turn",
		)
		await self.call(effects.withdraw_effect, cid, inst.id)

		with self.assertRaises(InvalidCharacterStateChange):
			await self.call(effects.suppress_effect, cid, inst.id)
		with self.assertRaises(InvalidCharacterStateChange):
			await self.call(effects.extend_effect, cid, inst.id, EffectExtendIn(duration_delta=1))

	# ---------- отсутствие цели/экземпляра ----------

	async def test_operations_on_missing_instance_raise(self):
		cid = await self.new_target()

		with self.assertRaises(CharacterNotFound):
			await self.call(effects.withdraw_effect, cid, uuid4())

	async def test_operations_on_missing_target_raise(self):
		"""Отсутствующая цель объясняется ошибкой поиска, а не TypeError (§12)."""
		missing = uuid4()

		with self.assertRaises(CharacterNotFound):
			await self.apply(
				missing, source_type="effect", modifiers=[mod("strength", 2)]
			)

	# ---------- чтение экземпляров ----------

	async def test_read_instances_includes_withdrawn(self):
		cid = await self.new_target()
		first = await self.apply(cid, source_type="effect", source_id=str(uuid4()), modifiers=[mod("strength", 2)])
		await self.apply(cid, source_type="effect", source_id=str(uuid4()), modifiers=[mod("dexterity", 1)])
		await self.call(effects.withdraw_effect, cid, first.id)

		read = await self.call(effects.read_effect_instances, cid)
		self.assertEqual(len(read.items), 2)
		self.assertEqual({item.status for item in read.items}, {"active", "withdrawn"})


if __name__ == "__main__":
	unittest.main()
