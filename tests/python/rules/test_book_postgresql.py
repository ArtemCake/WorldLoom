# tests/python/rules/test_book_postgresql.py

"""Проверки миграции книг и зависимостей на отдельной PostgreSQL."""

from __future__ import annotations
import importlib
import os
import unittest
from uuid import uuid4
import asyncio
from backend.app.modules.rules import errors
from backend.app.modules.rules.models.articles import RuleArticle, RuleArticleVersion
from backend.app.modules.rules.services import book_service
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import delete, func, insert, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from backend.app.modules.rules.models.books import RuleBook, RuleBookDraft, RuleBookVersion, RuleBookVersionArticle
from backend.app.modules.rules.schemas import articles as article_contracts
from backend.app.modules.rules.schemas import books as book_contracts
from backend.app.modules.rules.services import article_service
from backend.app.modules.rules.schemas.catalog import CatalogQuery
from backend.app.modules.rules.services import book_reader_service, catalog_service
from types import SimpleNamespace
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from backend.app.infrastructure.database.session import get_async_session
from backend.app.modules.admin.dependencies import require_content_manager
from backend.app.modules.auth.dependencies import get_current_user
from backend.app.modules.rules.api import router as rules_router
from backend.app.web.csrf import enforce_csrf
from backend.app.modules.rules import errors
from backend.app.modules.rules.schemas import system_books as system_contracts
from backend.app.modules.rules.schemas.catalog import CatalogQuery
from backend.app.modules.rules.services import catalog_service, system_books


BOOKS = RuleBook.__table__
DRAFTS = RuleBookDraft.__table__
VERSIONS = RuleBookVersion.__table__
DEPENDENCIES = RuleBookVersionArticle.__table__

MIGRATIONS = (
    "backend.db_migrations.versions.1372661e8ac9_созданиепроекта",
    "backend.db_migrations.versions.20261111_rule_books",
)


def database_url():
    raw = os.environ.get("WORLDLOOM_RULES_TEST_URL")

    if not raw:
        raise unittest.SkipTest("Не задан WORLDLOOM_RULES_TEST_URL; проверки PostgreSQL не выполнялись")

    try:
        url = make_url(raw)
    except Exception:
        raise RuntimeError("Некорректный формат WORLDLOOM_RULES_TEST_URL") from None

    if url.drivername != "postgresql+asyncpg":
        raise RuntimeError("Для тестов требуется подключение postgresql+asyncpg")

    if not url.database or not url.database.endswith(("_test", "_tests")):
        raise RuntimeError("Имя отдельной тестовой БД должно заканчиваться на _test или _tests")

    return url


def apply_migrations(connection):
    context = MigrationContext.configure(connection)

    with Operations.context(context):
        for module_name in MIGRATIONS:
            importlib.import_module(module_name).upgrade()


def sqlstate(error: DBAPIError):
    return getattr(error.orig, "sqlstate", None) or getattr(error.orig, "pgcode", None)


class BookPostgreSQLTests(unittest.IsolatedAsyncioTestCase):

    async def test_catalog_filters_books_by_system_before_pagination(self):
        article_id = await self.create_article_version()
        content = self.book_content([article_id])
        first_system = await self.create_test_system()
        second_system = await self.create_test_system()
        book_ids = []

        for _ in range(3):
            book_id = await self.create_book(content)
            await self.publish_directly(book_id, content)
            book_ids.append(book_id)

        await self.assign_test_system(book_ids[0], first_system)
        await self.assign_test_system(book_ids[1], second_system)

        async with self.sessions.begin() as session:
            page = await catalog_service.list_books(
                session,
                self.owner_id,
                CatalogQuery(limit=1),
                system_id=first_system,
            )

        self.assertEqual([item.id for item in page.items], [book_ids[0]])
        self.assertIsNone(page.next_after)

    async def test_catalog_hides_books_of_inactive_system(self):
        article_id = await self.create_article_version()
        content = self.book_content([article_id])
        book_id = await self.create_book(content)
        await self.publish_directly(book_id, content)
        system_id = await self.create_test_system()

        await self.assign_test_system(book_id, system_id)

        async with self.sessions.begin() as session:
            await session.execute(
                text("UPDATE game_systems SET is_active = false WHERE id = :id"),
                {"id": system_id},
            )

        async with self.sessions.begin() as session:
            page = await catalog_service.list_books(
                session,
                self.owner_id,
                CatalogQuery(),
                system_id=system_id,
            )

        self.assertEqual(page.items, [])
        self.assertIsNone(page.next_after)

    async def create_test_system(self, *, active=True):
        system_id = uuid4()

        async with self.sessions.begin() as session:
            await session.execute(
                text("INSERT INTO game_systems (id, is_active) VALUES (:id, :active)"),
                {"id": system_id, "active": active},
            )

        return system_id

    async def read_book_system(self, book_id):
        statement = select(BOOKS.c.system_id).where(BOOKS.c.id == book_id)

        async with self.sessions() as session:
            return (await session.execute(statement)).scalar_one()

    async def assign_test_system(self, book_id, system_id, *, revision=1, actor_id=None):
        data = system_contracts.BookSystemAssign(system_id=system_id, expected_revision=revision)

        async with self.sessions.begin() as session:
            return await system_books.assign_book_system(session, book_id, actor_id or self.owner_id, data)

    async def test_unassigned_book_is_preserved(self):
        book_id = await self.create_book(self.book_content([]))

        self.assertIsNone(await self.read_book_system(book_id))

    async def test_system_assignment_advances_draft_revision(self):
        book_id = await self.create_book(self.book_content([]))
        system_id = await self.create_test_system()

        result = await self.assign_test_system(book_id, system_id)

        self.assertEqual(result.book_id, book_id)
        self.assertEqual(result.system_id, system_id)
        self.assertEqual(result.draft_revision, 2)
        self.assertEqual(await self.read_book_system(book_id), system_id)

    async def test_system_assignment_requires_owner(self):
        book_id = await self.create_book(self.book_content([]))
        system_id = await self.create_test_system()

        with self.assertRaises(errors.RuleBookNotFound):
            await self.assign_test_system(book_id, system_id, actor_id=uuid4())

        self.assertIsNone(await self.read_book_system(book_id))

    async def test_system_assignment_rejects_stale_revision(self):
        book_id = await self.create_book(self.book_content([]))
        system_id = await self.create_test_system()

        with self.assertRaises(errors.RuleBookConflict):
            await self.assign_test_system(book_id, system_id, revision=2)

        self.assertIsNone(await self.read_book_system(book_id))

    async def test_system_assignment_rejects_inactive_system(self):
        book_id = await self.create_book(self.book_content([]))
        system_id = await self.create_test_system(active=False)

        with self.assertRaises(errors.RuleBookNotFound):
            await self.assign_test_system(book_id, system_id)

        self.assertIsNone(await self.read_book_system(book_id))

    async def test_system_assignment_rejects_missing_system(self):
        book_id = await self.create_book(self.book_content([]))

        with self.assertRaises(errors.RuleBookNotFound):
            await self.assign_test_system(book_id, uuid4())

        self.assertIsNone(await self.read_book_system(book_id))

    async def test_assigned_system_cannot_be_replaced(self):
        book_id = await self.create_book(self.book_content([]))
        first = await self.create_test_system()
        second = await self.create_test_system()

        await self.assign_test_system(book_id, first)

        with self.assertRaises(errors.RuleBookConflict):
            await self.assign_test_system(book_id, second, revision=2)

        self.assertEqual(await self.read_book_system(book_id), first)

    async def test_database_rejects_system_replacement_and_removal(self):
        book_id = await self.create_book(self.book_content([]))
        first = await self.create_test_system()
        second = await self.create_test_system()

        await self.assign_test_system(book_id, first)

        for target in (second, None):
            with self.subTest(target=target):
                statement = update(BOOKS).where(BOOKS.c.id == book_id).values(system_id=target)
                await self.expect_database_error(statement, "23514")

        self.assertEqual(await self.read_book_system(book_id), first)

    async def test_database_rejects_deletion_of_assigned_system(self):
        book_id = await self.create_book(self.book_content([]))
        system_id = await self.create_test_system()

        await self.assign_test_system(book_id, system_id)

        statement = text("DELETE FROM game_systems WHERE id = :id").bindparams(id=system_id)
        await self.expect_database_error(statement, "23503")

    async def test_assignment_does_not_rewrite_publication(self):
        article_id = await self.create_article_version()
        content = self.book_content([article_id])
        book_id = await self.create_book(content)
        version_id = await self.publish_directly(book_id, content)
        system_id = await self.create_test_system()

        await self.assign_test_system(book_id, system_id)

        statement = select(VERSIONS.c.content_json).where(VERSIONS.c.id == version_id)

        async with self.sessions() as session:
            saved = (await session.execute(statement)).scalar_one()

        self.assertEqual(saved, content.model_dump(mode="json"))
        self.assertEqual(await self.dependency_ids(version_id), {article_id})

    async def test_create_system_book_assigns_system_in_same_operation(self):
        system_id = await self.create_test_system()
        data = system_contracts.SystemBookCreate(
            system_id=system_id,
            slug=f"system-book-{uuid4().hex}",
            content=self.book_content([]),
        )

        async with self.sessions.begin() as session:
            created = await system_books.create_system_book(session, self.owner_id, data)

        self.assertEqual(created.book.system_id, system_id)
        self.assertEqual(created.draft.revision, 1)
        self.assertEqual(await self.read_book_system(created.book.id), system_id)

    async def test_create_system_book_rejects_missing_system_without_creating_book(self):
        before = await self.count_rows(BOOKS)
        data = system_contracts.SystemBookCreate(
            system_id=uuid4(),
            slug=f"missing-system-{uuid4().hex}",
            content=self.book_content([]),
        )

        with self.assertRaises(errors.RuleBookNotFound):
            async with self.sessions.begin() as session:
                await system_books.create_system_book(session, self.owner_id, data)

        self.assertEqual(await self.count_rows(BOOKS), before)

    async def test_assignment_is_rolled_back_with_outer_transaction(self):
        book_id = await self.create_book(self.book_content([]))
        system_id = await self.create_test_system()
        data = system_contracts.BookSystemAssign(system_id=system_id, expected_revision=1)

        with self.assertRaisesRegex(RuntimeError, "abort assignment"):
            async with self.sessions.begin() as session:
                await system_books.assign_book_system(session, book_id, self.owner_id, data)
                raise RuntimeError("abort assignment")

        self.assertIsNone(await self.read_book_system(book_id))

        async with self.sessions() as session:
            statement = select(DRAFTS.c.revision).where(DRAFTS.c.book_id == book_id)
            revision = (await session.execute(statement)).scalar_one()

        self.assertEqual(revision, 1)

    def rules_http_client(self, actor_id=None):
        app = FastAPI()
        app.include_router(rules_router)
        actor = SimpleNamespace(id=actor_id or self.owner_id)

        async def session_dependency():
            async with self.sessions() as session:
                yield session

        async def user_dependency():
            return actor

        async def csrf_dependency():
            return None

        app.dependency_overrides[get_async_session] = session_dependency
        app.dependency_overrides[get_current_user] = user_dependency
        app.dependency_overrides[require_content_manager] = user_dependency
        app.dependency_overrides[enforce_csrf] = csrf_dependency

        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def test_http_article_creation_commits_before_next_request(self):
        payload = {
            "slug": f"http-article-{uuid4().hex}",
            "content": {"title": "Статья через HTTP", "body": "Исходный текст"},
        }

        async with self.rules_http_client() as client:
            response = await client.post("/rules/articles", json=payload)

            self.assertEqual(response.status_code, 201, response.text)
            article_id = response.json()["article"]["id"]
            draft = await client.get(f"/rules/articles/{article_id}/draft")

        self.assertEqual(draft.status_code, 200, draft.text)
        self.assertEqual(draft.json()["revision"], 1)
        self.assertEqual(draft.json()["content_json"]["body"], "Исходный текст")

    async def test_http_stale_revision_does_not_overwrite_saved_article(self):
        payload = {
            "slug": f"http-conflict-{uuid4().hex}",
            "content": {"title": "Проверка ревизий", "body": "До сохранения"},
        }

        async with self.rules_http_client() as client:
            created = await client.post("/rules/articles", json=payload)
            self.assertEqual(created.status_code, 201, created.text)
            article_id = created.json()["article"]["id"]
            path = f"/rules/articles/{article_id}/draft"

            saved_payload = {
                "expected_revision": 1,
                "content": {"title": "Проверка ревизий", "body": "Сохранённый текст"},
            }
            saved = await client.put(path, json=saved_payload)
            self.assertEqual(saved.status_code, 200, saved.text)

            stale_payload = {
                "expected_revision": 1,
                "content": {"title": "Проверка ревизий", "body": "Устаревшая перезапись"},
            }
            conflict = await client.put(path, json=stale_payload)
            actual = await client.get(path)

        self.assertEqual(conflict.status_code, 409, conflict.text)
        self.assertEqual(actual.status_code, 200, actual.text)
        self.assertEqual(actual.json()["revision"], saved.json()["revision"])
        self.assertEqual(actual.json()["content_json"]["body"], "Сохранённый текст")

    async def test_http_article_publication_is_visible_in_catalog(self):
        payload = {
            "slug": f"http-published-{uuid4().hex}",
            "content": {"title": "Опубликованное правило", "body": "Текст публикации"},
        }

        async with self.rules_http_client() as client:
            created = await client.post("/rules/articles", json=payload)
            self.assertEqual(created.status_code, 201, created.text)
            article_id = created.json()["article"]["id"]

            response = await client.post(f"/rules/articles/{article_id}/publish", json={"expected_revision": 1})
            self.assertEqual(response.status_code, 200, response.text)
            publication = response.json()["publication"]

            catalog = await client.get("/rules/articles", params={"scope": "mine"})
            version = await client.get(f"/rules/articles/{article_id}/versions/{publication['id']}")

        self.assertEqual(catalog.status_code, 200, catalog.text)
        self.assertEqual(version.status_code, 200, version.text)
        self.assertEqual([item["version_id"] for item in catalog.json()["items"]], [publication["id"]])
        self.assertEqual(version.json()["content_json"]["body"], "Текст публикации")

    async def test_http_book_publication_pins_article_and_can_be_read(self):
        article_version_id = await self.create_article_version()
        content = self.book_content([article_version_id])
        payload = {"slug": f"http-book-{uuid4().hex}", "content": content.model_dump(mode="json")}

        async with self.rules_http_client() as client:
            created = await client.post("/rules/books", json=payload)
            self.assertEqual(created.status_code, 201, created.text)
            book_id = created.json()["book"]["id"]

            response = await client.post(f"/rules/books/{book_id}/publish", json={"expected_revision": 1})
            self.assertEqual(response.status_code, 200, response.text)
            publication = response.json()["publication"]

            reading = await client.get(f"/rules/books/{book_id}/versions/{publication['id']}/reading")

        self.assertEqual(reading.status_code, 200, reading.text)
        data = reading.json()
        self.assertEqual(data["publication"]["id"], publication["id"])
        self.assertEqual([item["id"] for item in data["articles"]], [str(article_version_id)])
        self.assertEqual(data["toc"][0]["article_version_id"], str(article_version_id))

        self.assertEqual(await self.count_rows(VERSIONS), 1)
        self.assertEqual(await self.count_rows(DEPENDENCIES), 1)

    async def test_http_failed_book_publication_leaves_no_partial_rows(self):
        missing_version_id = uuid4()
        content = self.book_content([missing_version_id])
        payload = {"slug": f"http-invalid-book-{uuid4().hex}", "content": content.model_dump(mode="json")}

        async with self.rules_http_client() as client:
            created = await client.post("/rules/books", json=payload)
            self.assertEqual(created.status_code, 201, created.text)
            book_id = created.json()["book"]["id"]

            response = await client.post(f"/rules/books/{book_id}/publish", json={"expected_revision": 1})
            draft = await client.get(f"/rules/books/{book_id}/draft")

        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(await self.count_rows(VERSIONS), 0)
        self.assertEqual(await self.count_rows(DEPENDENCIES), 0)
        self.assertEqual(draft.status_code, 200, draft.text)
        self.assertEqual(draft.json()["revision"], 1)

    async def test_http_owner_check_is_not_replaced_by_editor_permission(self):
        version_id = await self.create_article_version()
        created = await self.create_service_book([version_id])
        reader_id = await self.add_reader()

        async with self.rules_http_client(actor_id=reader_id) as client:
            response = await client.get(f"/rules/books/{created.book.id}/draft")

        self.assertEqual(response.status_code, 404, response.text)

    async def article_catalog(self, actor_id=None, **filters):
        actor_id = actor_id or self.owner_id

        async with self.sessions.begin() as session:
            return await catalog_service.list_articles(session, actor_id, CatalogQuery(**filters))

    async def book_catalog(self, actor_id=None, **filters):
        actor_id = actor_id or self.owner_id

        async with self.sessions.begin() as session:
            return await catalog_service.list_books(session, actor_id, CatalogQuery(**filters))

    async def read_service_book(self, book_id, version_id, actor_id=None):
        actor_id = actor_id or self.owner_id

        async with self.sessions.begin() as session:
            return await book_reader_service.read_book(session, book_id, version_id, actor_id)

    async def create_named_article(self, title, *, visibility="private", edition_key=None, language="ru"):
        values = {
            "title": title,
            "body": f"Текст: {title}",
            "edition_key": edition_key,
            "language": language,
        }
        content = article_contracts.ArticleContent(**values)
        data = article_contracts.RuleArticleCreate(slug=f"named-{uuid4().hex}", visibility=visibility, content=content)

        async with self.sessions.begin() as session:
            created = await article_service.create_article(session, self.owner_id, data)
            request = article_contracts.RuleArticlePublish(expected_revision=1)
            published = await article_service.publish_article(session, created.article.id, self.owner_id, request)

        return created.article.id, published.publication.id

    async def test_catalog_article_access_and_mine_scope(self):
        own_id, private_version = await self.create_named_article("Приватная статья")
        public_id, public_version = await self.create_named_article("Публичная статья", visibility="public")
        reader_id = await self.add_reader()

        own = await self.article_catalog(scope="mine")
        available = await self.article_catalog(actor_id=reader_id)
        readers_own = await self.article_catalog(actor_id=reader_id, scope="mine")

        self.assertEqual({item.id for item in own.items}, {own_id, public_id})
        self.assertEqual({item.version_id for item in available.items}, {public_version})
        self.assertNotIn(private_version, {item.version_id for item in available.items})
        self.assertEqual(readers_own.items, [])

    async def test_catalog_does_not_include_unpublished_article(self):
        content = article_contracts.ArticleContent(title="Только черновик")
        data = article_contracts.RuleArticleCreate(slug=f"draft-{uuid4().hex}", content=content)

        async with self.sessions.begin() as session:
            await article_service.create_article(session, self.owner_id, data)

        page = await self.article_catalog()

        self.assertEqual(page.items, [])

    async def test_catalog_filters_edition_and_language(self):
        wanted_id, wanted_version = await self.create_named_article("Проверки", edition_key="dnd5e-2014")
        await self.create_named_article("Другой язык", edition_key="dnd5e-2014", language="en")
        await self.create_named_article("Другая редакция", edition_key="dnd5e-2024")

        page = await self.article_catalog(edition_key="dnd5e-2014", language="ru")

        self.assertEqual([item.id for item in page.items], [wanted_id])
        self.assertEqual(page.items[0].version_id, wanted_version)

    async def test_catalog_search_treats_percent_and_underscore_literally(self):
        wanted_id, _ = await self.create_named_article("Порог 100%_точно")
        await self.create_named_article("Порог 1000 и другие значения")

        page = await self.article_catalog(q="100%_")

        self.assertEqual([item.id for item in page.items], [wanted_id])

    async def test_catalog_filters_latest_publication_not_older_matching_one(self):
        article_id, _ = await self.create_named_article("Старый заголовок")
        content = article_contracts.ArticleContent(title="Новый заголовок", body="Новый текст")
        update_request = article_contracts.RuleArticleDraftUpdate(expected_revision=2, content=content)

        async with self.sessions.begin() as session:
            saved = await article_service.update_article_draft(session, article_id, self.owner_id, update_request)
            publish_request = article_contracts.RuleArticlePublish(expected_revision=saved.revision)
            published = await article_service.publish_article(session, article_id, self.owner_id, publish_request)

        old_page = await self.article_catalog(q="Старый заголовок")
        new_page = await self.article_catalog(q="Новый заголовок")

        self.assertEqual(old_page.items, [])
        self.assertEqual(len(new_page.items), 1)
        self.assertEqual(new_page.items[0].version_id, published.publication.id)
        self.assertEqual(new_page.items[0].version_number, 2)

    async def test_catalog_keyset_pagination_has_no_duplicates(self):
        created = [await self.create_named_article(f"Статья {number}") for number in range(3)]
        expected = {article_id for article_id, _ in created}

        first = await self.article_catalog(limit=2)

        self.assertEqual(len(first.items), 2)
        self.assertIsNotNone(first.next_after)

        second = await self.article_catalog(limit=2, after=first.next_after)
        actual = [item.id for item in first.items + second.items]

        self.assertEqual(len(actual), 3)
        self.assertEqual(set(actual), expected)
        self.assertEqual(len(actual), len(set(actual)))
        self.assertIsNone(second.next_after)

    async def test_catalog_excludes_inactive_articles(self):
        _, version_id = await self.create_named_article("Архивная статья", visibility="public")
        await self.change_article_access(version_id, visibility="public", active=False)

        page = await self.article_catalog()

        self.assertEqual(page.items, [])

    async def test_book_catalog_excludes_unpublished_books(self):
        await self.create_service_book([])

        page = await self.book_catalog()

        self.assertEqual(page.items, [])

    async def test_book_catalog_and_reader_allow_public_book(self):
        _, article_version = await self.create_named_article("Открытое правило", visibility="public")
        created = await self.create_service_book([article_version], visibility="public")
        published = await self.publish_service_book(created.book.id)
        reader_id = await self.add_reader()

        page = await self.book_catalog(actor_id=reader_id)
        reading = await self.read_service_book(created.book.id, published.publication.id, actor_id=reader_id)

        self.assertEqual([item.id for item in page.items], [created.book.id])
        self.assertFalse(page.items[0].is_owned)
        self.assertEqual([article.id for article in reading.articles], [article_version])

    async def test_book_catalog_excludes_closed_source_before_pagination(self):
        _, closed_source = await self.create_named_article("Закрываемое правило", visibility="public")
        _, open_source = await self.create_named_article("Открытое правило", visibility="public")
        blocked = await self.create_service_book([closed_source], visibility="public")
        allowed = await self.create_service_book([open_source], visibility="public")
        await self.publish_service_book(blocked.book.id)
        await self.publish_service_book(allowed.book.id)
        reader_id = await self.add_reader()

        await self.change_article_access(closed_source, visibility="private")
        page = await self.book_catalog(actor_id=reader_id, limit=1)

        self.assertEqual([item.id for item in page.items], [allowed.book.id])
        self.assertIsNone(page.next_after)

    async def test_reader_does_not_bypass_private_book_access(self):
        version_id = await self.create_article_version()
        created = await self.create_service_book([version_id])
        published = await self.publish_service_book(created.book.id)
        reader_id = await self.add_reader()

        with self.assertRaises(errors.RuleBookNotFound):
            await self.read_service_book(created.book.id, published.publication.id, actor_id=reader_id)

    async def test_reader_sorts_toc_and_deduplicates_article_payload(self):
        _, article_version = await self.create_named_article("Исходное название")
        nodes = [
            {"kind": "article", "key": "repeat", "parent_key": None, "position": 1, "article_version_id": article_version},
            {"kind": "article", "key": "inside", "parent_key": "chapter", "position": 0, "article_version_id": article_version},
            {"kind": "chapter", "key": "chapter", "parent_key": None, "position": 0, "title": "Основы"},
        ]
        nodes[1]["title"] = "Название в книге"
        content = book_contracts.BookContent(title="Упорядоченная книга", toc=nodes)
        data = book_contracts.RuleBookCreate(slug=f"ordered-{uuid4().hex}", content=content)

        async with self.sessions.begin() as session:
            created = await book_service.create_book(session, self.owner_id, data)

        published = await self.publish_service_book(created.book.id)
        reading = await self.read_service_book(created.book.id, published.publication.id)

        self.assertEqual([node.key for node in reading.toc], ["chapter", "inside", "repeat"])
        self.assertEqual([node.depth for node in reading.toc], [0, 1, 0])
        self.assertEqual([node.title for node in reading.toc], ["Основы", "Название в книге", "Исходное название"])
        self.assertEqual([article.id for article in reading.articles], [article_version])
        self.assertEqual([node.key for node in reading.publication.content_json.toc], ["repeat", "inside", "chapter"])

    async def test_reader_preserves_pinned_article_version(self):
        article_id, first_version = await self.create_named_article("Первоначальное правило")
        created = await self.create_service_book([first_version])
        published_book = await self.publish_service_book(created.book.id)

        content = article_contracts.ArticleContent(title="Изменённое правило", body="Изменённый текст")
        update_request = article_contracts.RuleArticleDraftUpdate(expected_revision=2, content=content)

        async with self.sessions.begin() as session:
            saved = await article_service.update_article_draft(session, article_id, self.owner_id, update_request)
            request = article_contracts.RuleArticlePublish(expected_revision=saved.revision)
            next_publication = await article_service.publish_article(session, article_id, self.owner_id, request)

        reading = await self.read_service_book(created.book.id, published_book.publication.id)

        self.assertNotEqual(first_version, next_publication.publication.id)
        self.assertEqual(reading.articles[0].id, first_version)
        self.assertEqual(reading.articles[0].content_json.title, "Первоначальное правило")

    async def test_reader_rejects_book_after_source_becomes_inactive(self):
        version_id = await self.create_article_version()
        created = await self.create_service_book([version_id])
        published = await self.publish_service_book(created.book.id)

        await self.change_article_access(version_id, active=False)

        with self.assertRaises(errors.RuleBookNotFound):
            await self.read_service_book(created.book.id, published.publication.id)

    async def test_catalog_requires_transaction(self):
        async with self.sessions() as session:
            with self.assertRaises(RuntimeError):
                await catalog_service.list_articles(session, self.owner_id, CatalogQuery())

    async def test_catalog_revalidates_modified_query(self):
        query = CatalogQuery()
        query.limit = 0

        with self.assertRaises(catalog_service.InvalidCatalogQuery):
            async with self.sessions.begin() as session:
                await catalog_service.list_articles(session, self.owner_id, query)

    async def asyncSetUp(self):
        url = database_url()

        self.schema = f"wl_books_test_{uuid4().hex}"
        self.owner_id = uuid4()
        self.engine = None
        self.admin_engine = create_async_engine(url, poolclass=NullPool, hide_parameters=True)
        self.addAsyncCleanup(self.cleanup_database)

        async with self.admin_engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{self.schema}"'))

        settings = {
            "search_path": self.schema,
            "lock_timeout": "5000",
            "statement_timeout": "10000",
        }

        self.engine = create_async_engine(
            url,
            poolclass=NullPool,
            hide_parameters=True,
            isolation_level="READ COMMITTED",
            connect_args={"server_settings": settings},
        )
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

        async with self.engine.begin() as connection:
            await connection.execute(text("CREATE TABLE users (id uuid PRIMARY KEY)"))
            await connection.run_sync(apply_migrations)
            await connection.execute(text("INSERT INTO users (id) VALUES (:id)"), {"id": self.owner_id})
            await connection.execute(text(
                "CREATE TABLE game_systems ("
                "id uuid PRIMARY KEY, "
                "is_active boolean NOT NULL DEFAULT true)"
            ))

    async def cleanup_database(self):
        if self.engine is not None:
            await self.engine.dispose()

        try:
            async with self.admin_engine.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE'))
        finally:
            await self.admin_engine.dispose()

    async def create_article_version(self):
        content = article_contracts.ArticleContent(title="Проверки", body="Текст правила.")
        data = article_contracts.RuleArticleCreate(slug=f"article-{uuid4().hex}", content=content)

        async with self.sessions.begin() as session:
            created = await article_service.create_article(session, self.owner_id, data)
            request = article_contracts.RuleArticlePublish(expected_revision=1)
            published = await article_service.publish_article(session, created.article.id, self.owner_id, request)

        return published.publication.id

    def book_content(self, version_ids):
        toc = [
            {
                "kind": "article",
                "key": f"article-{position}",
                "parent_key": None,
                "position": position,
                "article_version_id": version_id,
            }
            for position, version_id in enumerate(version_ids)
        ]
        return book_contracts.BookContent(title="Книга правил", toc=toc)

    async def create_book(self, content):
        statement = insert(BOOKS).values(
            owner_id=self.owner_id,
            slug=f"book-{uuid4().hex}",
            visibility="private",
        ).returning(BOOKS.c.id)

        async with self.sessions.begin() as session:
            book_id = (await session.execute(statement)).scalar_one()
            await session.execute(insert(DRAFTS).values(
                book_id=book_id,
                revision=1,
                content_json=content.model_dump(mode="json"),
            ))

        return book_id

    def version_insert(self, book_id, content, *, version_number=1, source_revision=1):
        return insert(VERSIONS).values(
            book_id=book_id,
            version_number=version_number,
            source_draft_revision=source_revision,
            content_json=content.model_dump(mode="json"),
            published_by=self.owner_id,
        ).returning(VERSIONS.c.id)

    async def publish_directly(self, book_id, content, *, version_number=1, source_revision=1):
        statement = self.version_insert(
            book_id,
            content,
            version_number=version_number,
            source_revision=source_revision,
        )

        async with self.sessions.begin() as session:
            return (await session.execute(statement)).scalar_one()

    async def dependency_ids(self, version_id):
        statement = select(DEPENDENCIES.c.article_version_id).where(DEPENDENCIES.c.book_version_id == version_id)

        async with self.sessions() as session:
            return set((await session.execute(statement)).scalars())

    async def count_rows(self, table):
        async with self.sessions() as session:
            return (await session.execute(select(func.count()).select_from(table))).scalar_one()

    async def expect_database_error(self, statement, expected_state):
        with self.assertRaises(DBAPIError) as caught:
            async with self.sessions.begin() as session:
                await session.execute(statement)

        self.assertEqual(sqlstate(caught.exception), expected_state)

    async def test_migration_creates_tables(self):
        async with self.engine.connect() as connection:
            result = await connection.execute(text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = current_schema()"
            ))
            tables = set(result.scalars())

        expected = {"rule_books", "rule_book_drafts", "rule_book_versions", "rule_book_version_articles"}
        self.assertTrue(expected <= tables)

    async def test_empty_draft_is_allowed(self):
        content = self.book_content([])
        book_id = await self.create_book(content)

        async with self.sessions() as session:
            statement = select(DRAFTS.c.content_json).where(DRAFTS.c.book_id == book_id)
            payload = (await session.execute(statement)).scalar_one()

        self.assertEqual(payload["toc"], [])

    async def test_dependencies_are_created_automatically(self):
        first = await self.create_article_version()
        second = await self.create_article_version()
        content = self.book_content([first, second])
        book_id = await self.create_book(content)

        version_id = await self.publish_directly(book_id, content)

        self.assertEqual(await self.dependency_ids(version_id), {first, second})

    async def test_repeated_article_creates_single_dependency(self):
        article_id = await self.create_article_version()
        content = self.book_content([article_id, article_id])
        book_id = await self.create_book(content)

        version_id = await self.publish_directly(book_id, content)

        self.assertEqual(await self.dependency_ids(version_id), {article_id})

        async with self.sessions() as session:
            statement = select(VERSIONS.c.content_json).where(VERSIONS.c.id == version_id)
            payload = (await session.execute(statement)).scalar_one()

        self.assertEqual(len(payload["toc"]), 2)

    async def test_missing_article_rolls_back_entire_publication(self):
        existing = await self.create_article_version()
        content = self.book_content([existing, uuid4()])
        book_id = await self.create_book(content)

        await self.expect_database_error(self.version_insert(book_id, content), "23503")

        self.assertEqual(await self.count_rows(VERSIONS), 0)
        self.assertEqual(await self.count_rows(DEPENDENCIES), 0)

    async def test_empty_book_cannot_be_published(self):
        content = self.book_content([])
        book_id = await self.create_book(content)

        await self.expect_database_error(self.version_insert(book_id, content), "23514")

    async def test_foreign_dependency_cannot_be_added(self):
        included = await self.create_article_version()
        excluded = await self.create_article_version()
        content = self.book_content([included])
        book_id = await self.create_book(content)
        version_id = await self.publish_directly(book_id, content)

        statement = insert(DEPENDENCIES).values(book_version_id=version_id, article_version_id=excluded)
        await self.expect_database_error(statement, "23514")

        self.assertEqual(await self.dependency_ids(version_id), {included})

    async def test_existing_dependency_cannot_be_duplicated(self):
        article_id = await self.create_article_version()
        content = self.book_content([article_id])
        book_id = await self.create_book(content)
        version_id = await self.publish_directly(book_id, content)

        statement = insert(DEPENDENCIES).values(book_version_id=version_id, article_version_id=article_id)
        await self.expect_database_error(statement, "23505")

    async def test_publication_and_dependencies_are_immutable(self):
        article_id = await self.create_article_version()
        content = self.book_content([article_id])
        book_id = await self.create_book(content)
        version_id = await self.publish_directly(book_id, content)

        statements = (
            update(VERSIONS).where(VERSIONS.c.id == version_id).values(version_number=99),
            delete(VERSIONS).where(VERSIONS.c.id == version_id),
            text("TRUNCATE TABLE rule_book_versions CASCADE"),
            update(DEPENDENCIES).where(DEPENDENCIES.c.book_version_id == version_id).values(article_version_id=article_id),
            delete(DEPENDENCIES).where(DEPENDENCIES.c.book_version_id == version_id),
            text("TRUNCATE TABLE rule_book_version_articles"),
        )

        for number, statement in enumerate(statements):
            with self.subTest(operation=number):
                await self.expect_database_error(statement, "55000")

        self.assertEqual(await self.count_rows(VERSIONS), 1)
        self.assertEqual(await self.dependency_ids(version_id), {article_id})

    async def test_book_with_publication_cannot_be_deleted(self):
        article_id = await self.create_article_version()
        content = self.book_content([article_id])
        book_id = await self.create_book(content)
        await self.publish_directly(book_id, content)

        await self.expect_database_error(delete(BOOKS).where(BOOKS.c.id == book_id), "23503")

    async def test_duplicate_source_revision_is_rejected(self):
        article_id = await self.create_article_version()
        content = self.book_content([article_id])
        book_id = await self.create_book(content)
        await self.publish_directly(book_id, content)

        statement = self.version_insert(book_id, content, version_number=2, source_revision=1)
        await self.expect_database_error(statement, "23505")

    async def test_duplicate_version_number_is_rejected(self):
        article_id = await self.create_article_version()
        content = self.book_content([article_id])
        book_id = await self.create_book(content)
        await self.publish_directly(book_id, content)

        statement = self.version_insert(book_id, content, version_number=1, source_revision=2)
        await self.expect_database_error(statement, "23505")

    async def test_draft_changes_do_not_change_publication(self):
        article_id = await self.create_article_version()
        content = self.book_content([article_id])
        book_id = await self.create_book(content)
        version_id = await self.publish_directly(book_id, content)

        replacement = self.book_content([])
        replacement.title = "Другой черновик"

        async with self.sessions.begin() as session:
            await session.execute(
                update(DRAFTS)
                .where(DRAFTS.c.book_id == book_id)
                .values(content_json=replacement.model_dump(mode="json"), revision=2)
            )

        async with self.sessions() as session:
            statement = select(VERSIONS.c.content_json).where(VERSIONS.c.id == version_id)
            payload = (await session.execute(statement)).scalar_one()

        self.assertEqual(payload["title"], "Книга правил")
        self.assertEqual(await self.dependency_ids(version_id), {article_id})

    async def test_caller_rollback_removes_publication_and_dependencies(self):
        article_id = await self.create_article_version()
        content = self.book_content([article_id])
        book_id = await self.create_book(content)

        class AbortTransaction(Exception):
            pass

        with self.assertRaises(AbortTransaction):
            async with self.sessions.begin() as session:
                await session.execute(self.version_insert(book_id, content))
                raise AbortTransaction()

        self.assertEqual(await self.count_rows(VERSIONS), 0)
        self.assertEqual(await self.count_rows(DEPENDENCIES), 0)

    async def test_deleting_owner_preserves_snapshot_and_dependencies(self):
        article_id = await self.create_article_version()
        content = self.book_content([article_id])
        book_id = await self.create_book(content)
        version_id = await self.publish_directly(book_id, content)

        async with self.sessions.begin() as session:
            await session.execute(text("DELETE FROM users WHERE id = :id"), {"id": self.owner_id})

        async with self.sessions() as session:
            owner_query = select(BOOKS.c.owner_id).where(BOOKS.c.id == book_id)
            author_query = select(VERSIONS.c.published_by).where(VERSIONS.c.id == version_id)

            self.assertIsNone((await session.execute(owner_query)).scalar_one())
            self.assertEqual((await session.execute(author_query)).scalar_one(), self.owner_id)

        self.assertEqual(await self.dependency_ids(version_id), {article_id})

    async def create_service_book(self, version_ids, *, visibility="private", actor_id=None):
        actor_id = actor_id or self.owner_id
        data = book_contracts.RuleBookCreate(
            slug=f"service-book-{uuid4().hex}",
            visibility=visibility,
            content=self.book_content(version_ids),
        )

        async with self.sessions.begin() as session:
            return await book_service.create_book(session, actor_id, data)

    async def publish_service_book(self, book_id, revision=1):
        data = book_contracts.RuleBookPublish(expected_revision=revision)

        async with self.sessions.begin() as session:
            return await book_service.publish_book(session, book_id, self.owner_id, data)

    async def change_article_access(self, version_id, *, visibility="private", active=True):
        versions = RuleArticleVersion.__table__
        article_id = select(versions.c.article_id).where(versions.c.id == version_id).scalar_subquery()
        statement = (
            update(RuleArticle.__table__)
            .where(RuleArticle.__table__.c.id == article_id)
            .values(visibility=visibility, is_active=active)
        )

        async with self.sessions.begin() as session:
            await session.execute(statement)

    async def add_reader(self):
        actor_id = uuid4()

        async with self.sessions.begin() as session:
            await session.execute(text("INSERT INTO users (id) VALUES (:id)"), {"id": actor_id})

        return actor_id

    async def test_service_creates_book_and_first_draft(self):
        created = await self.create_service_book([])

        self.assertEqual(created.book.owner_id, self.owner_id)
        self.assertEqual(created.draft.book_id, created.book.id)
        self.assertEqual(created.draft.revision, 1)
        self.assertEqual(created.draft.content_json.toc, [])

    async def test_service_requires_caller_transaction(self):
        data = book_contracts.RuleBookCreate(slug="without-transaction", content=self.book_content([]))

        async with self.sessions() as session:
            with self.assertRaises(RuntimeError):
                await book_service.create_book(session, self.owner_id, data)

        self.assertEqual(await self.count_rows(BOOKS), 0)

    async def test_service_duplicate_slug_is_conflict(self):
        created = await self.create_service_book([])
        data = book_contracts.RuleBookCreate(slug=created.book.slug, content=self.book_content([]))

        with self.assertRaises(errors.RuleBookConflict):
            async with self.sessions.begin() as session:
                await book_service.create_book(session, self.owner_id, data)

        self.assertEqual(await self.count_rows(BOOKS), 1)
        self.assertEqual(await self.count_rows(DRAFTS), 1)

    async def test_service_rejects_missing_article_before_creation(self):
        with self.assertRaises(errors.RuleBookDependencyUnavailable):
            await self.create_service_book([uuid4()])

        self.assertEqual(await self.count_rows(BOOKS), 0)

    async def test_service_rejects_foreign_private_article(self):
        version_id = await self.create_article_version()
        reader_id = await self.add_reader()

        with self.assertRaises(errors.RuleBookDependencyUnavailable):
            await self.create_service_book([version_id], actor_id=reader_id)

        self.assertEqual(await self.count_rows(BOOKS), 0)

    async def test_service_accepts_foreign_public_article(self):
        version_id = await self.create_article_version()
        await self.change_article_access(version_id, visibility="public")
        reader_id = await self.add_reader()

        created = await self.create_service_book([version_id], actor_id=reader_id)

        self.assertEqual(created.book.owner_id, reader_id)

    async def test_service_public_draft_remains_owner_only(self):
        created = await self.create_service_book([], visibility="public")
        reader_id = await self.add_reader()

        with self.assertRaises(errors.RuleBookNotFound):
            async with self.sessions.begin() as session:
                await book_service.get_book_draft(session, created.book.id, reader_id)

    async def test_service_update_advances_revision(self):
        created = await self.create_service_book([])
        version_id = await self.create_article_version()
        data = book_contracts.RuleBookDraftUpdate(
            expected_revision=1,
            content=self.book_content([version_id]),
        )

        async with self.sessions.begin() as session:
            saved = await book_service.update_book_draft(session, created.book.id, self.owner_id, data)

        self.assertEqual(saved.revision, 2)
        self.assertEqual(saved.content_json.article_version_ids(), frozenset({version_id}))

    async def test_service_update_rejects_stale_revision(self):
        created = await self.create_service_book([])
        data = book_contracts.RuleBookDraftUpdate(expected_revision=1, content=self.book_content([]))

        async with self.sessions.begin() as session:
            await book_service.update_book_draft(session, created.book.id, self.owner_id, data)

        with self.assertRaises(errors.RuleBookConflict):
            async with self.sessions.begin() as session:
                await book_service.update_book_draft(session, created.book.id, self.owner_id, data)

    async def test_service_publish_builds_dependencies_and_advances_revision(self):
        version_id = await self.create_article_version()
        created = await self.create_service_book([version_id])
        published = await self.publish_service_book(created.book.id)

        self.assertEqual(published.publication.version_number, 1)
        self.assertEqual(published.publication.source_draft_revision, 1)
        self.assertEqual(published.publication.published_by, self.owner_id)
        self.assertEqual(published.draft_revision, 2)
        self.assertEqual(await self.dependency_ids(published.publication.id), {version_id})

    async def test_service_public_book_rejects_own_private_article(self):
        version_id = await self.create_article_version()
        created = await self.create_service_book([version_id], visibility="public")

        with self.assertRaises(errors.RuleBookDependencyUnavailable):
            await self.publish_service_book(created.book.id)

        self.assertEqual(await self.count_rows(VERSIONS), 0)
        self.assertEqual(await self.count_rows(DEPENDENCIES), 0)

    async def test_service_reader_can_read_public_book_with_public_sources(self):
        version_id = await self.create_article_version()
        await self.change_article_access(version_id, visibility="public")
        created = await self.create_service_book([version_id], visibility="public")
        published = await self.publish_service_book(created.book.id)
        reader_id = await self.add_reader()

        async with self.sessions.begin() as session:
            result = await book_service.get_book_version(
                session,
                created.book.id,
                published.publication.id,
                reader_id,
            )

        self.assertEqual(result.id, published.publication.id)

    async def test_service_closing_source_blocks_public_book_reading(self):
        version_id = await self.create_article_version()
        await self.change_article_access(version_id, visibility="public")
        created = await self.create_service_book([version_id], visibility="public")
        published = await self.publish_service_book(created.book.id)
        reader_id = await self.add_reader()

        await self.change_article_access(version_id, visibility="private")

        with self.assertRaises(errors.RuleBookNotFound):
            async with self.sessions.begin() as session:
                await book_service.get_book_version(
                    session,
                    created.book.id,
                    published.publication.id,
                    reader_id,
                )

        self.assertEqual(await self.count_rows(VERSIONS), 1)
        self.assertEqual(await self.dependency_ids(published.publication.id), {version_id})

    async def test_service_inactive_source_blocks_publication(self):
        version_id = await self.create_article_version()
        created = await self.create_service_book([version_id])

        await self.change_article_access(version_id, active=False)

        with self.assertRaises(errors.RuleBookDependencyUnavailable):
            await self.publish_service_book(created.book.id)

    async def test_service_owner_can_remove_unavailable_source(self):
        version_id = await self.create_article_version()
        created = await self.create_service_book([version_id])
        await self.change_article_access(version_id, active=False)

        async with self.sessions.begin() as session:
            draft = await book_service.get_book_draft(session, created.book.id, self.owner_id)

        data = book_contracts.RuleBookDraftUpdate(
            expected_revision=draft.revision,
            content=self.book_content([]),
        )

        async with self.sessions.begin() as session:
            saved = await book_service.update_book_draft(session, created.book.id, self.owner_id, data)

        self.assertEqual(saved.revision, 2)
        self.assertEqual(saved.content_json.toc, [])

    async def test_service_empty_book_cannot_be_published(self):
        created = await self.create_service_book([])

        with self.assertRaises(errors.RuleBookConflict):
            await self.publish_service_book(created.book.id)

    async def test_service_version_must_belong_to_requested_book(self):
        version_id = await self.create_article_version()
        first = await self.create_service_book([version_id])
        second = await self.create_service_book([])
        published = await self.publish_service_book(first.book.id)

        with self.assertRaises(errors.RuleBookNotFound):
            async with self.sessions.begin() as session:
                await book_service.get_book_version(
                    session,
                    second.book.id,
                    published.publication.id,
                    self.owner_id,
                )

    async def test_service_publication_rolls_back_with_revision(self):
        version_id = await self.create_article_version()
        created = await self.create_service_book([version_id])

        class AbortTransaction(Exception):
            pass

        with self.assertRaises(AbortTransaction):
            async with self.sessions.begin() as session:
                data = book_contracts.RuleBookPublish(expected_revision=1)
                await book_service.publish_book(session, created.book.id, self.owner_id, data)
                raise AbortTransaction()

        async with self.sessions.begin() as session:
            draft = await book_service.get_book_draft(session, created.book.id, self.owner_id)

        self.assertEqual(draft.revision, 1)
        self.assertEqual(await self.count_rows(VERSIONS), 0)
        self.assertEqual(await self.count_rows(DEPENDENCIES), 0)

    async def test_service_concurrent_updates_accept_one_revision(self):
        created = await self.create_service_book([])

        async def save(title):
            content = self.book_content([])
            content.title = title
            data = book_contracts.RuleBookDraftUpdate(expected_revision=1, content=content)

            try:
                async with self.sessions.begin() as session:
                    return await book_service.update_book_draft(session, created.book.id, self.owner_id, data)
            except errors.RuleBookConflict:
                return None

        results = await asyncio.wait_for(asyncio.gather(save("Первый вариант"), save("Второй вариант")), timeout=15)
        successful = [result for result in results if result is not None]

        self.assertEqual(len(successful), 1)

        async with self.sessions.begin() as session:
            draft = await book_service.get_book_draft(session, created.book.id, self.owner_id)

        self.assertEqual(draft.revision, 2)
        self.assertEqual(draft.content_json.title, successful[0].content_json.title)

    async def test_service_concurrent_publications_create_one_snapshot(self):
        version_id = await self.create_article_version()
        created = await self.create_service_book([version_id])

        async def publish_once():
            try:
                return await self.publish_service_book(created.book.id)
            except errors.RuleBookConflict:
                return None

        results = await asyncio.wait_for(asyncio.gather(publish_once(), publish_once()), timeout=15)
        successful = [result for result in results if result is not None]

        self.assertEqual(len(successful), 1)
        self.assertEqual(await self.count_rows(VERSIONS), 1)
        self.assertEqual(await self.dependency_ids(successful[0].publication.id), {version_id})


if __name__ == "__main__":
    unittest.main()
