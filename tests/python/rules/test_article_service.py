# tests/python/rules/test_article_service.py

"""Модульные тесты сервиса статей без подключения к БД."""

import unittest

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from backend.app.modules.rules import errors
from backend.app.modules.rules.schemas import articles as contracts
from backend.app.modules.rules.services import article_service as service


def row_result(row):
    result = MagicMock()
    result.mappings.return_value.one.return_value = row
    result.mappings.return_value.one_or_none.return_value = row
    return result


def scalar_result(value):
    result = MagicMock()
    result.scalar_one.return_value = value
    return result


def make_session(results):
    bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    return SimpleNamespace(
        new=(),
        dirty=(),
        deleted=(),
        get_bind=lambda: bind,
        execute=AsyncMock(side_effect=results),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )


class ArticleServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.actor_id = uuid4()
        self.article_id = uuid4()
        self.version_id = uuid4()
        self.now = datetime.now(timezone.utc)
        self.content = contracts.ArticleContent(title="Проверки", body="Текст правила.", edition_key="dnd5e-2014")
        self.payload = self.content.model_dump(mode="json")

        self.article = {
            "id": self.article_id,
            "owner_id": self.actor_id,
            "slug": "ability-checks",
            "visibility": "private",
            "is_active": True,
            "created_at": self.now,
            "updated_at": self.now,
        }

        self.draft = {
            "id": uuid4(),
            "article_id": self.article_id,
            "revision": 1,
            "content_json": self.payload,
            "created_at": self.now,
            "updated_at": self.now,
        }

        self.version = {
            "id": self.version_id,
            "article_id": self.article_id,
            "version_number": 1,
            "source_draft_revision": 1,
            "content_json": self.payload,
            "published_by": self.actor_id,
            "published_at": self.now,
        }

    async def test_create_article_and_draft(self):
        session = make_session([row_result(self.article), row_result(self.draft)])
        data = contracts.RuleArticleCreate(slug="ability-checks", content=self.content)

        result = await service.create_article(session, self.actor_id, data)

        self.assertEqual(result.article.id, self.article_id)
        self.assertEqual(result.draft.revision, 1)
        self.assertEqual(result.draft.content_json, self.content)

        statement = session.execute.await_args_list[1].args[0]
        self.assertEqual(statement.compile().params["content_json"], self.payload)

        session.commit.assert_not_awaited()
        session.rollback.assert_not_awaited()

    async def test_duplicate_slug_is_conflict(self):
        session = make_session([row_result(None)])
        data = contracts.RuleArticleCreate(slug="ability-checks", content=self.content)

        with self.assertRaises(errors.RuleArticleConflict):
            await service.create_article(session, self.actor_id, data)

        self.assertEqual(session.execute.await_count, 1)

    async def test_owner_can_read_draft(self):
        session = make_session([row_result(self.article), row_result(self.draft)])

        result = await service.get_article_draft(session, self.article_id, self.actor_id)

        self.assertEqual(result.content_json.body, "Текст правила.")

    async def test_public_article_does_not_expose_foreign_draft(self):
        article = {**self.article, "visibility": "public"}
        session = make_session([row_result(article)])

        with self.assertRaises(errors.RuleArticleNotFound):
            await service.get_article_draft(session, self.article_id, uuid4())

        self.assertEqual(session.execute.await_count, 1)

    async def test_update_rejects_stale_revision(self):
        session = make_session([row_result(self.article), row_result(self.draft)])
        data = contracts.RuleArticleDraftUpdate(expected_revision=2, content=self.content)

        with self.assertRaises(errors.RuleArticleConflict):
            await service.update_article_draft(session, self.article_id, self.actor_id, data)

        self.assertEqual(session.execute.await_count, 2)

    async def test_update_saves_content_and_advances_revision(self):
        content = contracts.ArticleContent(title="Проверки", body="Новый текст.")
        saved = {**self.draft, "revision": 2, "content_json": content.model_dump(mode="json")}
        session = make_session([
            row_result(self.article),
            row_result(self.draft),
            row_result(saved),
            row_result(None),
        ])
        data = contracts.RuleArticleDraftUpdate(expected_revision=1, content=content)

        result = await service.update_article_draft(session, self.article_id, self.actor_id, data)

        self.assertEqual(result.revision, 2)
        self.assertEqual(result.content_json.body, "Новый текст.")

        statement = session.execute.await_args_list[2].args[0]
        self.assertEqual(statement.compile().params["content_json"], content.model_dump(mode="json"))

    async def test_missing_updated_row_is_conflict(self):
        session = make_session([
            row_result(self.article),
            row_result(self.draft),
            row_result(None),
        ])
        data = contracts.RuleArticleDraftUpdate(expected_revision=1, content=self.content)

        with self.assertRaises(errors.RuleArticleConflict):
            await service.update_article_draft(session, self.article_id, self.actor_id, data)

    async def test_unknown_stored_schema_is_not_overwritten(self):
        payload = {**self.payload, "schema_version": 2}
        draft = {**self.draft, "content_json": payload}
        session = make_session([row_result(self.article), row_result(draft)])
        data = contracts.RuleArticleDraftUpdate(expected_revision=1, content=self.content)

        with self.assertRaises(errors.RuleArticleStorageError):
            await service.update_article_draft(session, self.article_id, self.actor_id, data)

        self.assertEqual(session.execute.await_count, 2)

    async def test_publish_saved_draft(self):
        advanced = {**self.draft, "revision": 2}
        session = make_session([
            row_result(self.article),
            row_result(self.draft),
            scalar_result(1),
            row_result(self.version),
            row_result(advanced),
            row_result(None),
        ])
        data = contracts.RuleArticlePublish(expected_revision=1)

        result = await service.publish_article(session, self.article_id, self.actor_id, data)

        self.assertEqual(result.publication.source_draft_revision, 1)
        self.assertEqual(result.draft_revision, 2)

        statement = session.execute.await_args_list[3].args[0]
        params = statement.compile().params

        self.assertEqual(params["content_json"], self.payload)
        self.assertEqual(params["published_by"], self.actor_id)
        self.assertEqual(params["source_draft_revision"], 1)

        session.commit.assert_not_awaited()
        session.rollback.assert_not_awaited()

    async def test_publish_rejects_stale_revision(self):
        advanced = {**self.draft, "revision": 2}
        session = make_session([row_result(self.article), row_result(advanced)])
        data = contracts.RuleArticlePublish(expected_revision=1)

        with self.assertRaises(errors.RuleArticleConflict):
            await service.publish_article(session, self.article_id, self.actor_id, data)

        self.assertEqual(session.execute.await_count, 2)

    async def test_publish_rejects_empty_text(self):
        payload = {**self.payload, "body": " \n "}
        draft = {**self.draft, "content_json": payload}
        session = make_session([row_result(self.article), row_result(draft)])
        data = contracts.RuleArticlePublish(expected_revision=1)

        with self.assertRaises(errors.RuleArticleConflict):
            await service.publish_article(session, self.article_id, self.actor_id, data)

        self.assertEqual(session.execute.await_count, 2)

    async def test_publish_rejects_inactive_article(self):
        article = {**self.article, "is_active": False}
        session = make_session([row_result(article)])
        data = contracts.RuleArticlePublish(expected_revision=1)

        with self.assertRaises(errors.RuleArticleConflict):
            await service.publish_article(session, self.article_id, self.actor_id, data)

        self.assertEqual(session.execute.await_count, 1)

    async def test_foreign_user_can_read_public_version(self):
        article = {**self.article, "visibility": "public"}
        session = make_session([row_result(article), row_result(self.version)])

        result = await service.get_article_version(session, self.article_id, self.version_id, uuid4())

        self.assertEqual(result.id, self.version_id)
        self.assertEqual(result.content_json, self.content)

    async def test_foreign_user_cannot_read_private_version(self):
        session = make_session([row_result(self.article)])

        with self.assertRaises(errors.RuleArticleNotFound):
            await service.get_article_version(session, self.article_id, self.version_id, uuid4())

        self.assertEqual(session.execute.await_count, 1)

    async def test_version_query_checks_article_and_version(self):
        session = make_session([row_result(self.article), row_result(None)])

        with self.assertRaises(errors.RuleArticleNotFound):
            await service.get_article_version(session, self.article_id, self.version_id, self.actor_id)

        statement = session.execute.await_args_list[1].args[0]
        values = statement.compile().params.values()

        self.assertIn(self.article_id, values)
        self.assertIn(self.version_id, values)

    async def test_dirty_session_is_rejected_before_query(self):
        session = make_session([])
        session.dirty = (object(),)

        with self.assertRaises(RuntimeError):
            await service.get_article_draft(session, self.article_id, self.actor_id)

        session.execute.assert_not_awaited()

    async def test_invalid_actor_is_rejected_before_query(self):
        session = make_session([])

        with self.assertRaises(errors.InvalidRuleArticle):
            await service.get_article_draft(session, self.article_id, "untrusted-user")

        session.execute.assert_not_awaited()

    async def test_mutated_request_is_revalidated(self):
        session = make_session([])
        data = contracts.RuleArticleDraftUpdate(expected_revision=1, content=self.content)
        data.expected_revision = 0

        with self.assertRaises(errors.InvalidRuleArticle):
            await service.update_article_draft(session, self.article_id, self.actor_id, data)

        session.execute.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
