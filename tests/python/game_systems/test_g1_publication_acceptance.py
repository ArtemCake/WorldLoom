# tests/python/game_systems/test_g1_publication_acceptance.py

"""Приёмка существующей публикации правил системы (§27-G).

§27-G требует три свойства выпуска. Здесь проверяются те, что
реализованы в пути editor_service.publish_rules_version:

- конфликт ревизии не теряет изменения: отказ происходит до записи,
  черновик остаётся прежним, версия не вставляется;
- выпуск воспроизводим: состав публикации — детерминированная
  функция от сохранённого черновика, а не от тела запроса;
- публикация берёт сохранённый черновик, новый профиль из запроса
  не принимается.

Публикация создаёт версию механики, версию текста (при непустых
главах) и комплект, поэтому моки отдают результаты в новом порядке.

Свойство «обновление источника не меняет публикацию» на уровне СУБД
проверяется неизменяемостью таблиц версий; оно НЕ эмулируется
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
from backend.app.modules.game_systems.rules.mechanic_codec import (
	profile_to_mechanic,
	profile_to_text,
)
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
	"""Приёмка §27-G для пути публикации правил."""

	def setUp(self):
		self.system_id = uuid4()
		self.now = datetime.now(timezone.utc)
		self.active_system = {
			"id": self.system_id,
			"is_active": True,
			"rules_engine_version": "1.0",
		}

	def _pair(self, rules_json: dict | None = None, revision: int = 1):
		"""Пара черновиков механики и текста из единого профиля."""
		payload = _profile_data() if rules_json is None else rules_json
		mechanic = {
			"id": uuid4(),
			"system_id": self.system_id,
			"revision": revision,
			"engine_version_id": None,
			"mechanic_overrides_json": None,
			"mechanic_json": profile_to_mechanic(payload),
			"created_at": self.now,
			"updated_at": self.now,
		}
		text = {
			"id": uuid4(),
			"system_id": self.system_id,
			"revision": revision,
			"text_json": profile_to_text(payload),
			"created_at": self.now,
			"updated_at": self.now,
		}
		return mechanic, text

	def _stub(self, mechanic: dict, text: dict, system: dict) -> None:
		"""Подменить загрузку системы и пары черновиков без обращения к БД."""

		async def get_system(*args, **kwargs):
			return system

		async def find_rows(*args, **kwargs):
			return mechanic, text

		self._patch(editor_service, "_get_system", get_system)
		self._patch(editor_service, "_find_draft_rows", find_rows)

	def _patch(self, target, name, replacement) -> None:
		original = getattr(target, name)
		setattr(target, name, replacement)
		self.addCleanup(setattr, target, name, original)

	def _mechanic_version_row(self, version_number: int = 1) -> dict:
		return {
			"id": uuid4(),
			"system_id": self.system_id,
			"version_number": version_number,
			"source_draft_revision": 1,
			"engine_version_id": None,
			"mechanic_overrides_json": None,
			"mechanic_json": profile_to_mechanic(_profile_data()),
			"rules_engine_version": "1.0",
			"published_at": self.now,
		}

	def _bundle_row(self, version_number: int = 1, mechanic_id=None, text_id=None) -> dict:
		return {
			"id": uuid4(),
			"system_id": self.system_id,
			"version_number": version_number,
			"text_version_id": text_id,
			"mechanic_version_id": mechanic_id or uuid4(),
			"published_at": self.now,
		}

	def _publish_results(self, *, revision_result=2, chapters: bool = False) -> list:
		"""Результаты запросов публикации в порядке выполнения.

		Порядок: номер механики, вставка механики, [номер и вставка
		текста], номер комплекта, вставка комплекта, закрепление текущей
		версии, потребление ревизии механики, потребление ревизии текста.
		"""
		mechanic_row = self._mechanic_version_row()
		results = [_scalar_result(0), _row_result(mechanic_row)]

		if chapters:
			results.append(_scalar_result(0))
			results.append(_row_result({
				"id": uuid4(),
				"system_id": self.system_id,
				"version_number": 1,
				"source_draft_revision": 1,
				"text_json": {"schema_version": 1, "chapters": {"main": {"label": "Глава"}}},
				"published_at": self.now,
			}))

		results.append(_scalar_result(0))
		results.append(_row_result(self._bundle_row(mechanic_id=mechanic_row["id"])))
		results.append(_scalar_result(None))
		results.append(_scalar_result(revision_result))
		results.append(_scalar_result(None))

		return results

	# ---------- конфликт ревизии не теряет изменения ----------

	def test_stale_revision_conflicts_before_any_write(self):
		"""Устаревшая ревизия отклоняется до обращения к БД (§27-G)."""
		mechanic, text = self._pair(revision=1)
		self._stub(mechanic, text, self.active_system)
		session = _make_session([])

		# Черновик на ревизии 1, а запрос ожидает 2.
		with self.assertRaises(GameSystemRulesConflict):
			asyncio.run(editor_service.publish_rules_version(
				session, self.system_id, GameSystemRulesPublish(expected_revision=2)
			))

		# Отказ произошёл до записи: запросов к БД не было вовсе.
		session.execute.assert_not_called()
		# Черновик не потерял изменения: ревизия и состав прежние.
		self.assertEqual(mechanic["revision"], 1)
		self.assertEqual(mechanic["mechanic_json"], profile_to_mechanic(_profile_data()))

	def test_concurrent_revision_change_does_not_publish(self):
		"""Если черновик изменился во время публикации, версия не создаётся (§27-G)."""
		mechanic, text = self._pair()
		self._stub(mechanic, text, self.active_system)

		# Потребление ревизии механики не находит строку по expected_revision.
		session = _make_session(self._publish_results(revision_result=None))

		with self.assertRaises(GameSystemRulesConflict):
			asyncio.run(editor_service.publish_rules_version(
				session, self.system_id, GameSystemRulesPublish(expected_revision=1)
			))

		# Потребление ревизии — шестой запрос; после отказа потребление
		# текста не выполняется.
		self.assertEqual(session.execute.await_count, 6)

	# ---------- выпуск воспроизводим ----------

	def test_published_content_is_deterministic_from_draft(self):
		"""Состав публикации — детерминированная функция черновика (§27-G)."""
		first = editor_service._rules_payload(_profile_data())
		second = editor_service._rules_payload(_profile_data())

		self.assertEqual(first, second)
		self.assertEqual(first["initial_attributes"]["divisor"], 2)

	def test_publish_uses_saved_draft_not_request_body(self):
		"""Публикация берёт сохранённый черновик; профиль из тела не принимается (§27-G)."""
		mechanic, text = self._pair()
		self._stub(mechanic, text, self.active_system)
		session = _make_session(self._publish_results())

		# В контракте публикации нет поля с правилами — только ревизия.
		fields = set(GameSystemRulesPublish.model_fields)
		self.assertNotIn("rules", fields)

		response = asyncio.run(editor_service.publish_rules_version(
			session, self.system_id, GameSystemRulesPublish(expected_revision=1)
		))

		# Выпуск соответствует снимку черновика.
		self.assertEqual(
			response.rules.model_dump(mode="json"),
			editor_service._rules_payload(_profile_data()),
		)
		self.assertEqual(response.version_number, 1)
		self.assertEqual(response.rules_engine_version, "1.0")

	def test_inactive_system_cannot_publish(self):
		"""Неактивная система не публикуется до любых операций (§27-G)."""
		mechanic, text = self._pair()
		inactive = dict(self.active_system, is_active=False)
		self._stub(mechanic, text, inactive)
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

		mechanic, text = self._pair(rules_json=bad)
		self._stub(mechanic, text, self.active_system)
		session = _make_session([])

		with self.assertRaises(GameSystemRulesConflict):
			asyncio.run(editor_service.publish_rules_version(
				session, self.system_id, GameSystemRulesPublish(expected_revision=1)
			))

		# Проверка состава предшествует записи: версия не вставлялась.
		session.execute.assert_not_called()

	def test_publication_with_chapters_creates_text_version(self):
		"""Непустые главы публикуются отдельной версией текста (§30#4)."""
		payload = dict(
			_profile_data(),
			rulebook={"main": {"label": "Глава"}},
		)
		mechanic, text = self._pair(rules_json=payload)
		self._stub(mechanic, text, self.active_system)
		session = _make_session(self._publish_results(chapters=True))

		response = asyncio.run(editor_service.publish_rules_version(
			session, self.system_id, GameSystemRulesPublish(expected_revision=1)
		))

		self.assertEqual(response.rules.rulebook["main"].label, "Глава")


if __name__ == "__main__":
	unittest.main()
