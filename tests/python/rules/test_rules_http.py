# tests/python/rules/test_rules_http.py

"""Проверки HTTP-границы без подключения к PostgreSQL."""

from __future__ import annotations
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from backend.app.modules.rules.services import system_books as system_book_service
from backend.app.infrastructure.database.session import get_async_session
from backend.app.modules.admin.dependencies import require_content_manager
from backend.app.modules.auth.dependencies import get_current_user
from backend.app.modules.rules import errors
from backend.app.modules.rules.api import router
from backend.app.modules.rules.http import rules_operation
from backend.app.modules.rules.schemas.catalog import CatalogPage
from backend.app.modules.rules.services import article_service, catalog_service
from backend.app.modules.rules.services.books import book_service, book_reader_service, book_authoring
from backend.app.web.csrf import enforce_csrf
from backend.app.modules.rules.schemas.books.book_authoring import AuthorBookPage


class FakeSession:
	def __init__(self):
		self.new = set()
		self.dirty = set()
		self.deleted = set()
		self.active = True
		self.nested = False
		self.begin = AsyncMock(side_effect=self._begin)
		self.commit = AsyncMock(side_effect=self._finish)
		self.rollback = AsyncMock(side_effect=self._finish)

	def in_transaction(self):
		return self.active

	def in_nested_transaction(self):
		return self.nested

	async def _begin(self):
		self.active = True

	async def _finish(self):
		self.active = False

class RulesHttpTests(unittest.IsolatedAsyncioTestCase):

	async def test_author_catalog_passes_authenticated_owner_and_filters(self):
		system_id = uuid4()
		mock = AsyncMock(return_value=AuthorBookPage(items=[]))

		with patch.object(book_authoring, "list_author_books", mock):
			response = await self.client.get(
				"/rules/books/authoring",
				params={"system_id": str(system_id), "limit": 2},
			)

		self.assertEqual(response.status_code, 200, response.text)
		args = mock.await_args.args
		self.assertIs(args[0], self.session)
		self.assertEqual(args[1], self.actor.id)
		self.assertEqual(args[2].system_id, system_id)
		self.assertEqual(args[2].scope, "mine")
		self.assertEqual(args[2].limit, 2)
		self.assertEqual(response.headers["cache-control"], "no-store")
		self.session.commit.assert_not_awaited()
		self.session.rollback.assert_awaited_once()

	async def test_author_catalog_rejects_foreign_owner_parameter(self):
		mock = AsyncMock(return_value=AuthorBookPage(items=[]))

		with patch.object(book_authoring, "list_author_books", mock):
			response = await self.client.get("/rules/books/authoring", params={"owner_id": str(uuid4())})

		self.assertEqual(response.status_code, 422)
		mock.assert_not_awaited()

	async def test_author_catalog_rejects_available_scope(self):
		mock = AsyncMock(return_value=AuthorBookPage(items=[]))

		with patch.object(book_authoring, "list_author_books", mock):
			response = await self.client.get("/rules/books/authoring", params={"scope": "available"})

		self.assertEqual(response.status_code, 422)
		mock.assert_not_awaited()

	async def test_author_catalog_requires_content_permission(self):
		del self.app.dependency_overrides[require_content_manager]
		mock = AsyncMock(return_value=AuthorBookPage(items=[]))

		with patch.object(book_authoring, "list_author_books", mock):
			response = await self.client.get("/rules/books/authoring")

		self.assertEqual(response.status_code, 403)
		mock.assert_not_awaited()

	async def test_book_editor_requires_content_permission(self):
		del self.app.dependency_overrides[require_content_manager]
		mock = AsyncMock()

		with patch.object(book_service, "get_book_editor", mock):
			response = await self.client.get(f"/rules/books/{uuid4()}/editor")

		self.assertEqual(response.status_code, 403)
		mock.assert_not_awaited()

	async def test_book_catalog_passes_system_separately_from_common_filters(self):
		system_id = uuid4()
		mock = AsyncMock(return_value=CatalogPage(items=[]))

		with patch.object(catalog_service, "list_books", mock):
			response = await self.client.get(
				"/rules/books",
				params={"system_id": str(system_id), "scope": "mine", "limit": 2},
			)

		self.assertEqual(response.status_code, 200, response.text)
		args = mock.await_args.args
		self.assertIs(args[0], self.session)
		self.assertEqual(args[1], self.actor.id)
		self.assertEqual(args[2].scope, "mine")
		self.assertEqual(args[2].limit, 2)
		self.assertNotIn("system_id", args[2].model_dump())
		self.assertEqual(mock.await_args.kwargs, {"system_id": system_id})
		self.session.commit.assert_not_awaited()
		self.session.rollback.assert_awaited_once()

	async def test_book_catalog_rejects_invalid_system_identifier(self):
		mock = AsyncMock(return_value=CatalogPage(items=[]))

		with patch.object(catalog_service, "list_books", mock):
			response = await self.client.get("/rules/books", params={"system_id": "invalid"})

		self.assertEqual(response.status_code, 422)
		mock.assert_not_awaited()

	async def test_article_catalog_does_not_accept_system_filter(self):
		mock = AsyncMock(return_value=CatalogPage(items=[]))

		with patch.object(catalog_service, "list_articles", mock):
			response = await self.client.get("/rules/articles", params={"system_id": str(uuid4())})

		self.assertEqual(response.status_code, 422)
		mock.assert_not_awaited()

	async def test_book_creation_without_system_never_calls_service(self):
		payload = {"slug": "book-without-system", "content": {"title": "Правила"}}
		mock = AsyncMock()

		with patch.object(system_book_service, "create_system_book", mock):
			response = await self.client.post("/rules/books", json=payload)

		self.assertEqual(response.status_code, 422)
		mock.assert_not_awaited()
		self.session.commit.assert_not_awaited()

	async def test_book_system_assignment_passes_actor_and_revision(self):
		book_id = uuid4()
		system_id = uuid4()
		result = {"book_id": book_id, "system_id": system_id, "draft_revision": 2}
		mock = AsyncMock(return_value=result)
		payload = {"system_id": str(system_id), "expected_revision": 1}

		with patch.object(system_book_service, "assign_book_system", mock):
			response = await self.client.put(f"/rules/books/{book_id}/system", json=payload)

		self.assertEqual(response.status_code, 200, response.text)
		args = mock.await_args.args
		self.assertIs(args[0], self.session)
		self.assertEqual(args[1], book_id)
		self.assertEqual(args[2], self.actor.id)
		self.assertEqual(args[3].system_id, system_id)
		self.assertEqual(args[3].expected_revision, 1)
		self.assertEqual(response.json()["draft_revision"], 2)
		self.assertEqual(response.headers["cache-control"], "no-store")
		self.session.commit.assert_awaited_once()
		self.session.rollback.assert_not_awaited()

	async def test_book_system_assignment_conflict_rolls_back(self):
		mock = AsyncMock(side_effect=errors.RuleBookConflict("Внутреннее описание конфликта"))
		payload = {"system_id": str(uuid4()), "expected_revision": 1}

		with patch.object(system_book_service, "assign_book_system", mock):
			response = await self.client.put(f"/rules/books/{uuid4()}/system", json=payload)

		self.assertEqual(response.status_code, 409)
		self.assertNotIn("Внутреннее описание", response.text)
		self.session.commit.assert_not_awaited()
		self.session.rollback.assert_awaited_once()

	async def test_book_system_assignment_requires_content_permission(self):
		del self.app.dependency_overrides[require_content_manager]
		mock = AsyncMock()
		payload = {"system_id": str(uuid4()), "expected_revision": 1}

		with patch.object(system_book_service, "assign_book_system", mock):
			response = await self.client.put(f"/rules/books/{uuid4()}/system", json=payload)

		self.assertEqual(response.status_code, 403)
		mock.assert_not_awaited()

	async def test_book_system_assignment_requires_csrf(self):
		async def deny_csrf():
			raise HTTPException(status_code=403, detail="Проверка CSRF не пройдена")

		self.app.dependency_overrides[enforce_csrf] = deny_csrf
		mock = AsyncMock()
		payload = {"system_id": str(uuid4()), "expected_revision": 1}

		with patch.object(system_book_service, "assign_book_system", mock):
			response = await self.client.put(f"/rules/books/{uuid4()}/system", json=payload)

		self.assertEqual(response.status_code, 403)
		mock.assert_not_awaited()
		self.session.commit.assert_not_awaited()

	async def asyncSetUp(self):
		self.session = FakeSession()
		self.actor = SimpleNamespace(id=uuid4(), roles=[], admin_permissions=[])
		self.app = FastAPI()
		self.app.include_router(router)

		async def session_dependency():
			yield self.session

		async def user_dependency():
			return self.actor

		async def csrf_dependency():
			return None

		self.app.dependency_overrides[get_async_session] = session_dependency
		self.app.dependency_overrides[get_current_user] = user_dependency
		self.app.dependency_overrides[require_content_manager] = user_dependency
		self.app.dependency_overrides[enforce_csrf] = csrf_dependency
		self.client = AsyncClient(transport=ASGITransport(app=self.app), base_url="http://test")

	async def asyncTearDown(self):
		await self.client.aclose()

	async def test_catalog_passes_actor_and_parses_query(self):
		result = CatalogPage(items=[])
		mock = AsyncMock(return_value=result)

		with patch.object(catalog_service, "list_articles", mock):
			response = await self.client.get("/rules/articles?limit=2&scope=mine&language=ru")

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json(), {"items": [], "next_after": None})
		self.assertEqual(response.headers["cache-control"], "no-store")
		args = mock.await_args.args
		self.assertIs(args[0], self.session)
		self.assertEqual(args[1], self.actor.id)
		self.assertEqual(args[2].limit, 2)
		self.assertEqual(args[2].scope, "mine")
		self.session.begin.assert_not_awaited()
		self.session.commit.assert_not_awaited()
		self.session.rollback.assert_awaited_once()

	async def test_book_catalog_has_separate_service(self):
		mock = AsyncMock(return_value=CatalogPage(items=[]))

		with patch.object(catalog_service, "list_books", mock):
			response = await self.client.get("/rules/books")

		self.assertEqual(response.status_code, 200)
		self.assertEqual(mock.await_args.args[1], self.actor.id)

	async def test_invalid_catalog_query_never_calls_service(self):
		mock = AsyncMock()

		with patch.object(catalog_service, "list_articles", mock):
			response = await self.client.get("/rules/articles?limit=0")

		self.assertEqual(response.status_code, 422)
		self.assertEqual(response.headers["cache-control"], "no-store")
		mock.assert_not_awaited()

	async def test_invalid_path_identifier_never_calls_service(self):
		mock = AsyncMock()

		with patch.object(article_service, "get_article_draft", mock):
			response = await self.client.get("/rules/articles/not-a-uuid/draft")

		self.assertEqual(response.status_code, 422)
		mock.assert_not_awaited()

	async def test_anonymous_catalog_is_unauthorized(self):
		del self.app.dependency_overrides[get_current_user]
		mock = AsyncMock()

		with patch.object(catalog_service, "list_articles", mock):
			response = await self.client.get("/rules/articles")

		self.assertEqual(response.status_code, 401)
		self.assertEqual(response.headers["www-authenticate"], "Bearer")
		self.assertEqual(response.headers["cache-control"], "no-store")
		mock.assert_not_awaited()

	async def test_reader_without_content_permission_cannot_open_draft(self):
		del self.app.dependency_overrides[require_content_manager]
		mock = AsyncMock()

		with patch.object(book_service, "get_book_draft", mock):
			response = await self.client.get(f"/rules/books/{uuid4()}/draft")

		self.assertEqual(response.status_code, 403)
		mock.assert_not_awaited()

	async def test_csrf_failure_blocks_publication(self):
		async def deny_csrf():
			raise HTTPException(status_code=403, detail="Проверка CSRF не пройдена")

		self.app.dependency_overrides[enforce_csrf] = deny_csrf
		mock = AsyncMock()

		with patch.object(book_service, "publish_book", mock):
			response = await self.client.post(f"/rules/books/{uuid4()}/publish", json={"expected_revision": 1})

		self.assertEqual(response.status_code, 403)
		mock.assert_not_awaited()
		self.session.commit.assert_not_awaited()

	async def test_publication_conflict_rolls_back(self):
		article_id = uuid4()
		mock = AsyncMock(side_effect=errors.RuleArticleConflict("Внутренний текст"))

		with patch.object(article_service, "publish_article", mock):
			response = await self.client.post(f"/rules/articles/{article_id}/publish", json={"expected_revision": 1})

		self.assertEqual(response.status_code, 409)
		self.assertNotIn("Внутренний текст", response.text)
		args = mock.await_args.args
		self.assertEqual(args[1], article_id)
		self.assertEqual(args[2], self.actor.id)
		self.assertEqual(args[3].expected_revision, 1)
		self.session.rollback.assert_awaited_once()
		self.session.commit.assert_not_awaited()

	async def test_missing_dependency_is_conflict(self):
		mock = AsyncMock(side_effect=errors.RuleBookDependencyUnavailable("Недоступная статья"))

		with patch.object(book_service, "publish_book", mock):
			response = await self.client.post(f"/rules/books/{uuid4()}/publish", json={"expected_revision": 1})

		self.assertEqual(response.status_code, 409)
		self.session.rollback.assert_awaited_once()

	async def test_reading_passes_both_identifiers_and_actor(self):
		book_id = uuid4()
		version_id = uuid4()
		mock = AsyncMock(side_effect=errors.RuleBookNotFound("Скрытая книга"))

		with patch.object(book_reader_service, "read_book", mock):
			response = await self.client.get(f"/rules/books/{book_id}/versions/{version_id}/reading")

		self.assertEqual(response.status_code, 404)
		mock.assert_awaited_once_with(self.session, book_id, version_id, self.actor.id)
		self.assertNotIn("Скрытая книга", response.text)

	async def test_unexpected_error_does_not_expose_exception(self):
		mock = AsyncMock(side_effect=RuntimeError("Секретное техническое значение"))

		with patch.object(catalog_service, "list_books", mock):
			response = await self.client.get("/rules/books")

		self.assertEqual(response.status_code, 500)
		self.assertNotIn("Секретное", response.text)
		self.assertEqual(response.headers["cache-control"], "no-store")
		self.session.rollback.assert_awaited_once()

	async def test_write_operation_commits_existing_transaction(self):
		async with rules_operation(self.session, write=True):
			self.assertTrue(self.session.in_transaction())

		self.session.begin.assert_not_awaited()
		self.session.commit.assert_awaited_once()
		self.session.rollback.assert_not_awaited()

	async def test_operation_opens_transaction_when_missing(self):
		self.session.active = False

		async with rules_operation(self.session):
			self.assertTrue(self.session.in_transaction())

		self.session.begin.assert_awaited_once()
		self.session.rollback.assert_awaited_once()

	async def test_commit_failure_rolls_back(self):
		self.session.commit.side_effect = RuntimeError("Не удалось зафиксировать")

		with self.assertRaises(RuntimeError):
			async with rules_operation(self.session, write=True):
				pass

		self.session.rollback.assert_awaited_once()

	async def test_cancellation_rolls_back(self):
		with self.assertRaises(asyncio.CancelledError):
			async with rules_operation(self.session, write=True):
				raise asyncio.CancelledError()

		self.session.rollback.assert_awaited_once()
		self.session.commit.assert_not_awaited()

	async def test_nested_transaction_is_rejected(self):
		self.session.nested = True

		with self.assertRaises(RuntimeError):
			async with rules_operation(self.session):
				self.fail("Операция не должна выполняться")

		self.session.rollback.assert_awaited_once()

	async def test_openapi_has_unique_operation_identifiers(self):
		schema = self.app.openapi()
		identifiers = []

		for item in schema["paths"].values():
			for method, operation in item.items():
				if method in {"get", "post", "put", "patch", "delete"}:
					identifiers.append(operation["operationId"])

		self.assertEqual(len(identifiers), len(set(identifiers)))
		self.assertIn("/rules/articles", schema["paths"])
		self.assertIn("/rules/books/{book_id}/versions/{version_id}/reading", schema["paths"])


if __name__ == "__main__":
	unittest.main()
