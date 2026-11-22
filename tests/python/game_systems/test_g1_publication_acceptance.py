# tests/python/game_systems/test_g1_publication_acceptance.py

"""Приёмка существующей публикации правил системы (§27-G).

§27-G требует три свойства выпуска. Здесь проверяются те, что
реализованы в существующем пути editor_service.publish_rules_version
и не требуют новых таблиц (то есть не зависят от §30#4/#5):

- конфликт ревизии не теряет изменения: отказ происходит до записи,
  черновик остаётся прежним, версия не вставляется;
- выпуск воспроизводим: состав публикации — детерминированная
  функция от сохранённого черновика, а не от тела запроса;
- публикация берёт сохранённый черновик, новый профиль из запроса
  не принимается.

Свойство «обновление источника не меняет публикацию» на уровне СУБД
проверяется неизменяемостью таблицы версий; оно НЕ эмулируется
моками, потому что подмена такого теста дала бы ложное подтверждение.
"""

from __future__ import annotations

import asyncio
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from backend.app.modules.game_systems.errors import GameSystemRulesConflict
from backend.app.modules.game_systems.schemas.game_rules import GameSystemRulesPublish
from backend.app.modules.game_systems.services import editor_service


def _profile_data(divisor: int = 2) -> dict:
	return {
		"schema_version": 4,
		"calculations": {"attributes": {
			"divisor": {
				"label": "Делитель",
				"field_type": "integer",
				"min_value": 0,
				"max_value": 10,
			},
		}, "derived": {}},
		"initial_attributes": {"divisor": divisor},
		"resources": {},
	}


def _row_result(row: dict):
	"""Мок строки запроса: mappings().one()/one_or_none() возвращают row."""

	class _Mappings:
		def one(self):
			return row

		def one_or_none(self):
			return row

	class _Result:
		def mappings(self):
			return _Mappings()

		def scalar_one(self):
			return row

		def scalar_one_or_none(self):
			return row

	return _Result()


def _scalar_result(value):
	"""Мок скалярного запроса (max version_number, обновлённая ревизия)."""

	class _Result:
		def scalar_one(self):
			return value

		def scalar_one_or_none(self):
			return value

	return _Result()


def _make_session(results: list) -> SimpleNamespace:
	"""Сессия, отдающая подготовленные результаты по порядку вызовов."""
	pending = iter(results)

	async def execute(*args, **kwargs):
		return next(pending)

	return SimpleNamespace(
		new=(),
		dirty=(),
		deleted=(),
		execute=AsyncMock(side_effect=execute),
	)


class G1PublicationAcceptanceTests(unittest.TestCase):
	"""Приёмка §27-G для уже реализованного пути публикации правил."""

	def setUp(self):
		self.system_id = uuid4()
		self.now = datetime.now(timezone.utc)
		self.draft = {
			"id": uuid4(),
			"system_id": self.system_id,
			"revision": 1,
			"rules_json": _profile_data(),
			"engine_version_id": None,
			"rules_overrides_json": None,
		}
		self.active_system = {
			"id": self.system_id,
			"is_active": True,
			"rules_engine_version": "1.0",
		}

	def _stub(self, draft: dict, system: dict) -> None:
		"""Подменить загрузку системы и черновика без обращения к БД."""

		async def get_system(*args, **kwargs):
			return system

		async def find_draft(*args, **kwargs):
			return draft

		self._patch(editor_service, "_get_system", get_system)
		self._patch(editor_service, "_find_draft", find_draft)

	def _patch(self, target, name, replacement) -> None:
		original = getattr(target, name)
		setattr(target, name, replacement)
		self.addCleanup(setattr, target, name, original)

	def _version_row(self, version_number: int = 1) -> dict:
		return {
			"id": uuid4(),
			"system_id": self.system_id,
			"version_number": version_number,
			"engine_version_id": None,
			"rules_overrides_json": None,
			"rules_json": editor_service._rules_payload(self.draft["rules_json"]),
			"rules_engine_version": "1.0",
			"published_at": self.now,
		}

	# ---------- конфликт ревизии не теряет изменения ----------

	def test_stale_revision_conflicts_before_any_write(self):
		"""Устаревшая ревизия отклоняется до обращения к БД (§27-G)."""
		draft = deepcopy(self.draft)
		self._stub(draft, self.active_system)
		session = _make_session([])

		# Черновик на ревизии 1, а запрос ожидает 2.
		with self.assertRaises(GameSystemRulesConflict):
			asyncio.run(editor_service.publish_rules_version(
				session, self.system_id, GameSystemRulesPublish(expected_revision=2)
			))

		# Отказ произошёл до записи: запросов к БД не было вовсе.
		session.execute.assert_not_called()
		# Черновик не потерял изменения: ревизия и состав прежние.
		self.assertEqual(draft["revision"], 1)
		self.assertEqual(draft["rules_json"], self.draft["rules_json"])

	def test_concurrent_revision_change_does_not_publish(self):
		"""Если черновик изменился во время публикации, версия не создаётся (§27-G)."""
		self._stub(self.draft, self.active_system)

		# max version_number, затем insert возвращает строку,
		# но update черновика не находит строку по expected_revision.
		session = _make_session([
			_scalar_result(0),
			_row_result(self._version_row(1)),
			_scalar_result(None),
		])

		with self.assertRaises(GameSystemRulesConflict):
			asyncio.run(editor_service.publish_rules_version(
				session, self.system_id, GameSystemRulesPublish(expected_revision=1)
			))

		# Три запроса были намечены, но транзакция у вызывающего:
		# отказ означает отсутствие зафиксированного выпуска.
		self.assertEqual(session.execute.await_count, 3)

	# ---------- выпуск воспроизводим ----------

	def test_published_content_is_deterministic_from_draft(self):
		"""Состав публикации — детерминированная функция черновика (§27-G)."""
		first = editor_service._rules_payload(self.draft["rules_json"])
		second = editor_service._rules_payload(self.draft["rules_json"])

		self.assertEqual(first, second)
		self.assertEqual(first["initial_attributes"]["divisor"], 2)

	def test_publish_uses_saved_draft_not_request_body(self):
		"""Публикация берёт сохранённый черновик; профиль из тела не принимается (§27-G)."""
		self._stub(self.draft, self.active_system)
		version_row = self._version_row(1)
		session = _make_session([
			_scalar_result(0),
			_row_result(version_row),
			_scalar_result(2),
		])

		# В контракте публикации нет поля с правилами — только ревизия.
		fields = set(GameSystemRulesPublish.model_fields)
		self.assertNotIn("rules", fields)

		response = asyncio.run(editor_service.publish_rules_version(
			session, self.system_id, GameSystemRulesPublish(expected_revision=1)
		))

		# Выпуск соответствует снимку черновика.
		self.assertEqual(
			response.rules.model_dump(mode="json"),
			editor_service._rules_payload(self.draft["rules_json"]),
		)
		self.assertEqual(response.version_number, 1)
		self.assertEqual(response.rules_engine_version, "1.0")

	def test_inactive_system_cannot_publish(self):
		"""Неактивная система не публикуется до любых операций (§27-G)."""
		inactive = dict(self.active_system, is_active=False)
		self._stub(self.draft, inactive)
		session = _make_session([])

		with self.assertRaises(GameSystemRulesConflict):
			asyncio.run(editor_service.publish_rules_version(
				session, self.system_id, GameSystemRulesPublish(expected_revision=1)
			))

		session.execute.assert_not_called()

	def test_non_executable_draft_rejected_before_write(self):
		"""Неисполняемый черновик отклоняется до вставки версии (§27-G)."""
		# Формула с делением на ноль делает профиль неисполняемым.
		bad = {
			"schema_version": 4,
			"calculations": {"attributes": {
				"divisor": {
					"label": "Делитель",
					"field_type": "integer",
					"min_value": 0,
					"max_value": 10,
				},
			}, "derived": {
				"result": {
					"label": "Результат",
					"formula": {"operation": "floor_div", "arguments": [10, "attribute.divisor"]},
				},
			}},
			"initial_attributes": {"divisor": 0},
			"resources": {},
		}

		draft = dict(self.draft, rules_json=bad)
		self._stub(draft, self.active_system)
		session = _make_session([])

		with self.assertRaises(GameSystemRulesConflict):
			asyncio.run(editor_service.publish_rules_version(
				session, self.system_id, GameSystemRulesPublish(expected_revision=1)
			))

		# Проверка состава предшествует записи: версия не вставлялась.
		session.execute.assert_not_called()


if __name__ == "__main__":
	unittest.main()
