# tests/python/rules/test_system_catalog.py

"""Проверки запроса вариантов систем для HTML-каталога."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from backend.app.modules.rules.services.system_catalog import list_active_system_options


class SystemCatalogTests(unittest.IsolatedAsyncioTestCase):
	async def test_returns_only_identifiers_and_names(self):
		system_id = uuid4()
		result = Mock()
		result.mappings.return_value.all.return_value = [{"id": system_id, "name": "Тестовая система"}]
		session = SimpleNamespace(execute=AsyncMock(return_value=result))

		options = await list_active_system_options(session)

		self.assertEqual(options, [{"id": str(system_id), "name": "Тестовая система"}])
		session.execute.assert_awaited_once()

		statement = session.execute.await_args.args[0]
		self.assertEqual(list(statement.selected_columns.keys()), ["id", "name"])

		sql = str(statement.compile(dialect=postgresql.dialect()))
		self.assertIn("game_systems.is_active IS true", sql)
		self.assertIn("ORDER BY lower(game_systems.name), game_systems.id", sql)

	async def test_empty_result_returns_empty_options(self):
		result = Mock()
		result.mappings.return_value.all.return_value = []
		session = SimpleNamespace(execute=AsyncMock(return_value=result))

		self.assertEqual(await list_active_system_options(session), [])


if __name__ == "__main__":
	unittest.main()
