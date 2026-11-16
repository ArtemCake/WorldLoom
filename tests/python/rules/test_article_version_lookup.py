# tests/python/rules/test_article_version_lookup.py

"""Проверки поиска публикации и делегирования существующей проверке доступа."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4
from backend.app.modules.rules import errors
from backend.app.modules.rules.services import article_version_lookup as service


class ArticleVersionLookupTests(unittest.IsolatedAsyncioTestCase):
	def session(self, article_id):
		result = Mock()
		result.scalar_one_or_none.return_value = article_id
		session = SimpleNamespace(
			new=set(),
			dirty=set(),
			deleted=set(),
			execute=AsyncMock(return_value=result),
			get_bind=Mock(return_value=SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))),
			commit=AsyncMock(),
			rollback=AsyncMock(),
		)
		return session

	async def test_exact_publication_is_read_through_existing_access_check(self):
		article_id, version_id, actor_id = uuid4(), uuid4(), uuid4()
		session = self.session(article_id)
		expected = object()

		with patch.object(service, "get_article_version", AsyncMock(return_value=expected)) as reader:
			actual = await service.get_version_by_id(session, version_id, actor_id)

		self.assertIs(actual, expected)
		reader.assert_awaited_once_with(session, article_id, version_id, actor_id)
		statement = session.execute.await_args.args[0]
		self.assertEqual(list(statement.selected_columns.keys()), ["article_id"])
		self.assertIn(version_id, statement.compile().params.values())
		session.commit.assert_not_awaited()
		session.rollback.assert_not_awaited()

	async def test_missing_publication_does_not_call_reader(self):
		session = self.session(None)

		with patch.object(service, "get_article_version", AsyncMock()) as reader:
			with self.assertRaises(errors.RuleArticleNotFound):
				await service.get_version_by_id(session, uuid4(), uuid4())

		reader.assert_not_awaited()

	async def test_existing_access_denial_is_not_bypassed(self):
		session = self.session(uuid4())
		reader = AsyncMock(side_effect=errors.RuleArticleNotFound("Статья не найдена"))

		with patch.object(service, "get_article_version", reader):
			with self.assertRaises(errors.RuleArticleNotFound):
				await service.get_version_by_id(session, uuid4(), uuid4())

		reader.assert_awaited_once()
		session.commit.assert_not_awaited()

	async def test_pending_orm_changes_are_rejected_before_query(self):
		session = self.session(uuid4())
		session.dirty.add(object())

		with self.assertRaises(RuntimeError):
			await service.get_version_by_id(session, uuid4(), uuid4())

		session.execute.assert_not_awaited()

	async def test_invalid_identifiers_are_rejected_before_query(self):
		for version_id, actor_id in [("invalid", uuid4()), (uuid4(), "invalid")]:
			session = self.session(uuid4())

			with self.assertRaises(errors.InvalidRuleArticle):
				await service.get_version_by_id(session, version_id, actor_id)

			session.execute.assert_not_awaited()


if __name__ == "__main__":
	unittest.main()
