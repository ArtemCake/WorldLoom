# tests/python/rules/test_author_system_catalog.py

"""Проверки доступности систем для авторской мастерской."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4
from sqlalchemy.dialects import postgresql
from backend.app.modules.rules import errors
from backend.app.modules.rules.services import system_books, system_catalog


class AuthorSystemCatalogTests(unittest.IsolatedAsyncioTestCase):
	async def test_author_options_do_not_require_activity_or_publication(self):
		system_id = uuid4()
		result = Mock()
		result.mappings.return_value.all.return_value = [{"id": system_id, "name": "Система в разработке"}]
		session = SimpleNamespace(execute=AsyncMock(return_value=result))

		options = await system_catalog.list_author_system_options(session)

		self.assertEqual(options, [{"id": str(system_id), "name": "Система в разработке"}])
		session.execute.assert_awaited_once()

		statement = session.execute.await_args.args[0]
		sql = str(statement.compile(dialect=postgresql.dialect()))

		self.assertEqual(list(statement.selected_columns.keys()), ["id", "name"])
		self.assertNotIn("WHERE", sql)
		self.assertNotIn("JOIN", sql)
		self.assertNotIn("current_rules_version_id", sql)
		self.assertIn("ORDER BY lower(game_systems.name), game_systems.id", sql)

	async def test_author_options_can_be_empty(self):
		result = Mock()
		result.mappings.return_value.all.return_value = []
		session = SimpleNamespace(execute=AsyncMock(return_value=result))

		options = await system_catalog.list_author_system_options(session)

		self.assertEqual(options, [])

	async def test_reader_options_keep_activity_filter(self):
		result = Mock()
		result.mappings.return_value.all.return_value = []
		session = SimpleNamespace(execute=AsyncMock(return_value=result))

		await system_catalog.list_active_system_options(session)

		statement = session.execute.await_args.args[0]
		sql = str(statement.compile(dialect=postgresql.dialect()))

		self.assertIn("game_systems.is_active IS true", sql)

	async def test_authoring_system_check_requires_only_existing_container(self):
		system_id = uuid4()
		result = Mock()
		result.scalar_one_or_none.return_value = system_id
		session = SimpleNamespace(execute=AsyncMock(return_value=result))

		await system_books._system_for_authoring(session, system_id)

		session.execute.assert_awaited_once()
		statement = session.execute.await_args.args[0]
		compiled = statement.compile(dialect=postgresql.dialect())
		sql = str(compiled)

		self.assertIn(system_id, compiled.params.values())
		self.assertIn("game_systems.id =", sql)
		self.assertIn("FOR SHARE", sql)
		self.assertNotIn("is_active", sql)
		self.assertNotIn("current_rules_version_id", sql)
		self.assertNotIn("JOIN", sql)

	async def test_missing_system_is_still_rejected(self):
		result = Mock()
		result.scalar_one_or_none.return_value = None
		session = SimpleNamespace(execute=AsyncMock(return_value=result))

		with self.assertRaises(errors.RuleBookNotFound):
			await system_books._system_for_authoring(session, uuid4())


if __name__ == "__main__":
	unittest.main()
