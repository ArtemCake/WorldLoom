# tests/python/rules/test_article_postgresql.py

"""Интеграционные проверки статей на отдельной тестовой PostgreSQL.

Подключение берётся только из WORLDLOOM_RULES_TEST_URL.
Каждый тест использует собственную схему без доступа к public.
Проверяется миграция статей, а не вся цепочка миграций приложения.
"""

from __future__ import annotations
import asyncio
import importlib
import os
import unittest
from uuid import uuid4
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import delete, func, insert, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from backend.app.modules.rules import errors
from backend.app.modules.rules.models.articles import RuleArticle, RuleArticleDraft, RuleArticleVersion
from backend.app.modules.rules.schemas import articles as contracts
from backend.app.modules.rules.services import article_service as service


ARTICLES = RuleArticle.__table__
DRAFTS = RuleArticleDraft.__table__
VERSIONS = RuleArticleVersion.__table__

MIGRATION_MODULE = "backend.db_migrations.versions.1e297517fb5c_созданиепроекта"


def test_database_url():
    """Не использовать рабочие настройки и не выводить реквизиты подключения."""
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


# Не давать pytest считать вспомогательную функцию самостоятельным тестом.
test_database_url.__test__ = False


def apply_article_migration(connection):
    """Выполнить реальный upgrade миграции в текущей временной схеме."""
    migration = importlib.import_module(MIGRATION_MODULE)
    context = MigrationContext.configure(connection)

    with Operations.context(context):
        migration.upgrade()


def sqlstate(error: DBAPIError):
    return getattr(error.orig, "sqlstate", None) or getattr(error.orig, "pgcode", None)


class ArticlePostgreSQLTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        url = test_database_url()

        self.schema = f"wl_rules_test_{uuid4().hex}"
        self.owner_id = uuid4()
        self.other_id = uuid4()
        self.engine = None

        self.admin_engine = create_async_engine(url, poolclass=NullPool, hide_parameters=True)
        self.addAsyncCleanup(self.cleanup_database)

        async with self.admin_engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{self.schema}"'))

        server_settings = {
            "search_path": self.schema,
            "lock_timeout": "5000",
            "statement_timeout": "10000",
        }

        self.engine = create_async_engine(
            url,
            poolclass=NullPool,
            hide_parameters=True,
            isolation_level="READ COMMITTED",
            connect_args={"server_settings": server_settings},
        )
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

        async with self.engine.begin() as connection:
            await connection.execute(text("CREATE TABLE users (id uuid PRIMARY KEY)"))
            await connection.run_sync(apply_article_migration)

            statement = text("INSERT INTO users (id) VALUES (:owner), (:other)")
            await connection.execute(statement, {"owner": self.owner_id, "other": self.other_id})

    async def cleanup_database(self):
        if self.engine is not None:
            await self.engine.dispose()

        try:
            async with self.admin_engine.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE'))
        finally:
            await self.admin_engine.dispose()

    def content(self, body: str = "Текст правила.") -> contracts.ArticleContent:
        return contracts.ArticleContent(title="Проверки характеристик", body=body, edition_key="dnd5e-2014")

    async def create_article(self, *, visibility: str = "private", body: str = "Текст правила."):
        data = contracts.RuleArticleCreate(
            slug=f"article-{uuid4().hex}",
            visibility=visibility,
            content=self.content(body),
        )

        async with self.sessions.begin() as session:
            return await service.create_article(session, self.owner_id, data)

    async def publish(self, article_id, revision: int = 1):
        data = contracts.RuleArticlePublish(expected_revision=revision)

        async with self.sessions.begin() as session:
            return await service.publish_article(session, article_id, self.owner_id, data)

    async def count_versions(self, article_id) -> int:
        statement = select(func.count()).select_from(VERSIONS).where(VERSIONS.c.article_id == article_id)

        async with self.sessions() as session:
            return (await session.execute(statement)).scalar_one()

    async def expect_database_error(self, statement, expected_state: str):
        with self.assertRaises(DBAPIError) as caught:
            async with self.sessions.begin() as session:
                await session.execute(statement)

        self.assertEqual(sqlstate(caught.exception), expected_state)

    async def test_migration_creates_tables_and_enabled_guards(self):
        async with self.engine.connect() as connection:
            result = await connection.execute(text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = current_schema()"
            ))
            tables = set(result.scalars())

            result = await connection.execute(text(
                "SELECT t.tgname, t.tgenabled "
                "FROM pg_trigger AS t "
                "JOIN pg_class AS c ON c.oid = t.tgrelid "
                "JOIN pg_namespace AS n ON n.oid = c.relnamespace "
                "WHERE n.nspname = current_schema() "
                "AND c.relname = 'rule_article_versions' AND NOT t.tgisinternal"
            ))
            guards = dict(result.all())

        self.assertTrue({"rule_articles", "rule_article_drafts", "rule_article_versions"} <= tables)
        self.assertEqual(guards.get("rule_article_versions_immutable"), "O")
        self.assertEqual(guards.get("rule_article_versions_no_truncate"), "O")

    async def test_create_and_read_persisted_draft(self):
        created = await self.create_article()

        async with self.sessions.begin() as session:
            draft = await service.get_article_draft(session, created.article.id, self.owner_id)

        self.assertEqual(draft.revision, 1)
        self.assertEqual(draft.content_json, self.content())

    async def test_creation_is_rolled_back_with_caller_transaction(self):
        data = contracts.RuleArticleCreate(slug="rollback-create", content=self.content())

        class AbortTransaction(Exception):
            pass

        with self.assertRaises(AbortTransaction):
            async with self.sessions.begin() as session:
                await service.create_article(session, self.owner_id, data)
                raise AbortTransaction()

        async with self.sessions() as session:
            articles = (await session.execute(select(func.count()).select_from(ARTICLES))).scalar_one()
            drafts = (await session.execute(select(func.count()).select_from(DRAFTS))).scalar_one()

        self.assertEqual(articles, 0)
        self.assertEqual(drafts, 0)

    async def test_duplicate_slug_does_not_create_second_draft(self):
        created = await self.create_article()
        data = contracts.RuleArticleCreate(slug=created.article.slug, content=self.content())

        with self.assertRaises(errors.RuleArticleConflict):
            async with self.sessions.begin() as session:
                await service.create_article(session, self.owner_id, data)

        async with self.sessions() as session:
            drafts = (await session.execute(select(func.count()).select_from(DRAFTS))).scalar_one()

        self.assertEqual(drafts, 1)

    async def test_publication_keeps_snapshot_after_draft_edit(self):
        created = await self.create_article()
        published = await self.publish(created.article.id)

        data = contracts.RuleArticleDraftUpdate(
            expected_revision=published.draft_revision,
            content=self.content("Изменённый текст."),
        )

        async with self.sessions.begin() as session:
            draft = await service.update_article_draft(session, created.article.id, self.owner_id, data)

        async with self.sessions.begin() as session:
            version = await service.get_article_version(
                session,
                created.article.id,
                published.publication.id,
                self.owner_id,
            )

        self.assertEqual(draft.revision, 3)
        self.assertEqual(draft.content_json.body, "Изменённый текст.")
        self.assertEqual(version.content_json.body, "Текст правила.")
        self.assertEqual(version.source_draft_revision, 1)

    async def test_publication_and_revision_roll_back_together(self):
        created = await self.create_article()

        class AbortTransaction(Exception):
            pass

        with self.assertRaises(AbortTransaction):
            async with self.sessions.begin() as session:
                data = contracts.RuleArticlePublish(expected_revision=1)
                await service.publish_article(session, created.article.id, self.owner_id, data)
                raise AbortTransaction()

        async with self.sessions.begin() as session:
            draft = await service.get_article_draft(session, created.article.id, self.owner_id)

        self.assertEqual(draft.revision, 1)
        self.assertEqual(await self.count_versions(created.article.id), 0)

        published = await self.publish(created.article.id)
        self.assertEqual(published.publication.version_number, 1)

    async def test_same_revision_cannot_be_published_twice(self):
        created = await self.create_article()
        await self.publish(created.article.id)

        with self.assertRaises(errors.RuleArticleConflict):
            await self.publish(created.article.id, revision=1)

        self.assertEqual(await self.count_versions(created.article.id), 1)

    async def test_database_rejects_duplicate_source_revision(self):
        created = await self.create_article()
        published = await self.publish(created.article.id)

        statement = insert(VERSIONS).values(
            article_id=created.article.id,
            version_number=2,
            source_draft_revision=published.publication.source_draft_revision,
            content_json=self.content().model_dump(mode="json"),
            published_by=self.owner_id,
        )
        await self.expect_database_error(statement, "23505")

    async def test_empty_text_cannot_be_published(self):
        created = await self.create_article(body=" \n ")

        with self.assertRaises(errors.RuleArticleConflict):
            await self.publish(created.article.id)

        self.assertEqual(await self.count_versions(created.article.id), 0)

    async def test_database_also_rejects_empty_publication(self):
        created = await self.create_article()

        statement = insert(VERSIONS).values(
            article_id=created.article.id,
            version_number=1,
            source_draft_revision=1,
            content_json=self.content("   ").model_dump(mode="json"),
            published_by=self.owner_id,
        )
        await self.expect_database_error(statement, "23514")

    async def test_publication_rejects_update_delete_and_truncate(self):
        created = await self.create_article()
        published = await self.publish(created.article.id)
        version_id = published.publication.id

        statements = (
            update(VERSIONS).where(VERSIONS.c.id == version_id).values(version_number=99),
            delete(VERSIONS).where(VERSIONS.c.id == version_id),
            text("TRUNCATE TABLE rule_article_versions"),
        )

        for statement in statements:
            with self.subTest(operation=type(statement).__name__):
                await self.expect_database_error(statement, "55000")

        self.assertEqual(await self.count_versions(created.article.id), 1)

    async def test_article_with_publication_cannot_be_deleted(self):
        created = await self.create_article()
        await self.publish(created.article.id)

        statement = delete(ARTICLES).where(ARTICLES.c.id == created.article.id)
        await self.expect_database_error(statement, "23503")

        self.assertEqual(await self.count_versions(created.article.id), 1)

    async def test_deleting_owner_preserves_publication(self):
        created = await self.create_article(visibility="public")
        published = await self.publish(created.article.id)

        async with self.sessions.begin() as session:
            await session.execute(text("DELETE FROM users WHERE id = :id"), {"id": self.owner_id})

        async with self.sessions.begin() as session:
            version = await service.get_article_version(
                session,
                created.article.id,
                published.publication.id,
                self.other_id,
            )
            owner = await session.execute(select(ARTICLES.c.owner_id).where(ARTICLES.c.id == created.article.id))

            self.assertIsNone(owner.scalar_one())

        self.assertEqual(version.published_by, self.owner_id)
        self.assertEqual(version.content_json.body, "Текст правила.")

    async def test_foreign_reader_cannot_access_public_draft(self):
        created = await self.create_article(visibility="public")
        published = await self.publish(created.article.id)

        with self.assertRaises(errors.RuleArticleNotFound):
            async with self.sessions.begin() as session:
                await service.get_article_draft(session, created.article.id, self.other_id)

        async with self.sessions.begin() as session:
            version = await service.get_article_version(
                session,
                created.article.id,
                published.publication.id,
                self.other_id,
            )

        self.assertEqual(version.id, published.publication.id)

    async def test_version_of_another_article_is_not_returned(self):
        first = await self.create_article()
        second = await self.create_article()
        published = await self.publish(first.article.id)

        with self.assertRaises(errors.RuleArticleNotFound):
            async with self.sessions.begin() as session:
                await service.get_article_version(
                    session,
                    second.article.id,
                    published.publication.id,
                    self.owner_id,
                )

    async def test_concurrent_publish_accepts_only_one_expected_revision(self):
        created = await self.create_article()

        async def publish_once():
            try:
                return await self.publish(created.article.id, revision=1)
            except errors.RuleArticleConflict:
                return None

        results = await asyncio.wait_for(asyncio.gather(publish_once(), publish_once()), timeout=15)
        successful = [result for result in results if result is not None]

        self.assertEqual(len(successful), 1)
        self.assertEqual(successful[0].publication.version_number, 1)
        self.assertEqual(await self.count_versions(created.article.id), 1)

        async with self.sessions.begin() as session:
            draft = await service.get_article_draft(session, created.article.id, self.owner_id)

        self.assertEqual(draft.revision, 2)


if __name__ == "__main__":
    unittest.main()

