# tests/python/rules/test_book_postgresql.py

"""Проверки миграции книг и зависимостей на отдельной PostgreSQL."""

from __future__ import annotations
import importlib
import os
import unittest
from uuid import uuid4
import asyncio
from backend.app.modules.rules import errors
from backend.app.modules.rules.models.articles import RuleArticle
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


BOOKS = RuleBook.__table__
DRAFTS = RuleBookDraft.__table__
VERSIONS = RuleBookVersion.__table__
DEPENDENCIES = RuleBookVersionArticle.__table__

MIGRATIONS = (
    "backend.db_migrations.versions.20261111_rule_articles",
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
    from backend.app.modules.rules.models.articles import RuleArticleVersion

    articles = RuleArticle.__table__
    versions = RuleArticleVersion.__table__
    article_id = select(versions.c.article_id).where(versions.c.id == version_id).scalar_subquery()
    statement = (
        update(articles)
        .where(articles.c.id == article_id)
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
