# tests/python/rules/test_workspace_overview.py

"""Read-only обзор рабочего пространства системы (§5.1) на PostgreSQL.

Один сценарий на всех: пустая система -> черновик правил -> основа ->
книга -> публикация книги -> публикация системы. Проверяет, что обзор
агрегирует данные и ничего не записывает (read-only).
"""

from __future__ import annotations
import os
import unittest
from uuid import uuid4

from sqlalchemy import func, insert, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app.modules.game_systems.errors import GameSystemNotFound
from backend.app.modules.game_systems.models.game_systems import GameSystem
from backend.app.modules.game_systems.models.system_versions import (
	GameSystemMechanicDraft,
	GameSystemMechanicVersion,
	GameSystemVersion,
)
from backend.app.modules.game_systems.models.rule_engines import RuleEngine, RuleEngineVersion
from backend.app.modules.rules.models.books import RuleBook, RuleBookDraft, RuleBookVersion
from backend.app.modules.rules.schemas import articles as article_contracts
from backend.app.modules.rules.schemas.books import books as book_contracts
from backend.app.modules.rules.services import article_service, workspace_overview
from tests.python.rules.pg_support import (
	USER_INSERT_SQL,
	PostgresTestCase,
	apply_migrations,
	require_connection,
	system_values,
	user_values,
)


_SYSTEMS = GameSystem.__table__
_MECHANIC_DRAFTS = GameSystemMechanicDraft.__table__
_MECHANIC_VERSIONS = GameSystemMechanicVersion.__table__
_SYSTEM_VERSIONS = GameSystemVersion.__table__
_ENGINES = RuleEngine.__table__
_ENGINE_VERSIONS = RuleEngineVersion.__table__
_BOOKS = RuleBook.__table__
_BOOK_DRAFTS = RuleBookDraft.__table__
_BOOK_VERSIONS = RuleBookVersion.__table__

# Профиль движка-основы остаётся в формате правил (schema_version 4).
ENGINE_PROFILE = {
	"schema_version": 4,
	"calculations": {"attributes": {}, "derived": {}},
	"initial_attributes": {},
	"resources": {},
}

# Снимок механики системы: числовая часть без текстового раздела.
MECHANIC_SNAPSHOT = {
	"schema_version": 1,
	"calculations": {"attributes": {}, "derived": {}},
	"initial_attributes": {},
	"resources": {},
}


def database_url():
	raw = os.environ.get("WORLDLOOM_RULES_TEST_URL")

	if not raw:
		raise unittest.SkipTest("Не задан WORLDLOOM_RULES_TEST_URL; проверка PostgreSQL не выполнялась")

	url = make_url(raw)

	if url.drivername != "postgresql+asyncpg":
		raise RuntimeError("Для тестов требуется подключение postgresql+asyncpg")

	if not url.database or not url.database.endswith(("_test", "_tests")):
		raise RuntimeError("Имя отдельной тестовой БД должно заканчиваться на _test или _tests")

	return url


class WorkspaceOverviewPostgreSQLTests(PostgresTestCase):

	async def asyncSetUp(self):
		url = database_url()
		await require_connection(url)

		self.schema = f"wl_wsoverview_{uuid4().hex}"
		self.owner_id = uuid4()
		self.engine = None
		self.admin_engine = create_async_engine(url, poolclass=NullPool, hide_parameters=True)
		self.addAsyncCleanup(self.cleanup_database)

		async with self.admin_engine.begin() as connection:
			await connection.execute(text(f'CREATE SCHEMA "{self.schema}"'))

		self.engine = create_async_engine(
			url,
			poolclass=NullPool,
			hide_parameters=True,
			isolation_level="READ COMMITTED",
			connect_args={"server_settings": {"search_path": self.schema, "lock_timeout": "5000", "statement_timeout": "10000"}},
		)
		self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

		async with self.engine.begin() as connection:
			await connection.run_sync(apply_migrations)
			await connection.execute(USER_INSERT_SQL, user_values(self.owner_id))

	async def cleanup_database(self):
		if self.engine is not None:
			await self.engine.dispose()

		try:
			async with self.admin_engine.begin() as connection:
				await connection.execute(text(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE'))
		finally:
			await self.admin_engine.dispose()

	async def insert_system(self, *, active=True):
		values = system_values(active=active)

		async with self.sessions.begin() as session:
			await session.execute(
				insert(_SYSTEMS).values(
					id=values["id"],
					name=values["name"],
					slug=values["slug"],
					rules_engine_version="1.0",
					is_active=active,
				)
			)

		return values["id"]

	async def row_counts(self):
		async with self.sessions() as session:
			return {
				"systems": (await session.execute(select(func.count()).select_from(_SYSTEMS))).scalar_one(),
				"drafts": (await session.execute(select(func.count()).select_from(_MECHANIC_DRAFTS))).scalar_one(),
				"books": (await session.execute(select(func.count()).select_from(_BOOKS))).scalar_one(),
				"book_versions": (await session.execute(select(func.count()).select_from(_BOOK_VERSIONS))).scalar_one(),
			}

	async def create_published_article(self):
		content = article_contracts.ArticleContent(title="Проверки", body="Текст правила.")
		data = article_contracts.RuleArticleCreate(slug=f"article-{uuid4().hex}", content=content)

		async with self.sessions.begin() as session:
			created = await article_service.create_article(session, self.owner_id, data)
			published = await article_service.publish_article(
				session, created.article.id, self.owner_id, article_contracts.RuleArticlePublish(expected_revision=1)
			)

		return published.publication.id

	async def test_workspace_overview_aggregates_without_writing(self):
		# 1. Пустая система: нет черновика, нет книг.
		system_id = await self.insert_system()

		async with self.sessions() as session:
			empty = await workspace_overview.get_workspace_overview(session, system_id)

		self.assertEqual(empty.system.id, system_id)
		self.assertFalse(empty.rules_draft_present)
		self.assertFalse(empty.rules_published)
		self.assertEqual(empty.books_published, 0)
		self.assertEqual(empty.books, [])
		self.assertIsNone(empty.rules.draft)
		self.assertIsNone(empty.rules.engine)

		before = await self.row_counts()

		# 2. Черновик правил поверх основы движка (проверяет ветку engine).
		engine_version_id = uuid4()

		async with self.sessions.begin() as session:
			await session.execute(
				insert(_ENGINES).values(id=uuid4(), owner_id=self.owner_id, name="Движок", slug=f"engine-{uuid4().hex}", visibility="private")
			)
			await session.execute(
				insert(_ENGINE_VERSIONS).values(
					id=engine_version_id,
					engine_id=select(_ENGINES.c.id).scalar_subquery(),
					version_number=1,
					source_draft_revision=1,
					rules_json=ENGINE_PROFILE,
					rules_engine_version="1.0",
				)
			)
			await session.execute(
				insert(_MECHANIC_DRAFTS).values(
					system_id=system_id,
					revision=1,
					engine_version_id=engine_version_id,
					mechanic_overrides_json={"hp": 10},
					mechanic_json=MECHANIC_SNAPSHOT,
				)
			)

		async with self.sessions() as session:
			with_draft = await workspace_overview.get_workspace_overview(session, system_id)

		self.assertTrue(with_draft.rules_draft_present)
		self.assertEqual(with_draft.rules.draft.revision, 1)
		self.assertEqual(with_draft.rules.draft.rules_json["schema_version"], 4)
		self.assertIsNotNone(with_draft.rules.engine)
		self.assertEqual(with_draft.rules.engine.engine_version_id, engine_version_id)
		self.assertEqual(with_draft.rules.engine.rules_overrides_json, {"hp": 10})

		# 3. Книга без публикации: заголовок берётся из черновика книги.
		book_id = uuid4()
		book_content = book_contracts.BookContent(title="Книга правил", toc=[])

		async with self.sessions.begin() as session:
			await session.execute(
				insert(_BOOKS).values(id=book_id, owner_id=self.owner_id, system_id=system_id, slug=f"book-{uuid4().hex}", visibility="private")
			)
			await session.execute(
				insert(_BOOK_DRAFTS).values(book_id=book_id, revision=1, content_json=book_content.model_dump(mode="json"))
			)

		async with self.sessions() as session:
			with_book = await workspace_overview.get_workspace_overview(session, system_id)

		self.assertEqual(len(with_book.books), 1)
		self.assertEqual(with_book.books[0].title, "Книга правил")
		self.assertIsNone(with_book.books[0].latest_version)
		self.assertEqual(with_book.books_published, 0)

		# 4. Публикация книги: версия и дата появляются (CHECK требует статью в оглавлении).
		article_version_id = await self.create_published_article()
		published_content = book_contracts.BookContent(
			title="Книга правил",
			toc=[book_contracts.BookArticleNode(key="glava", position=0, article_version_id=article_version_id)],
		)

		async with self.sessions.begin() as session:
			await session.execute(
				insert(_BOOK_VERSIONS).values(
					id=uuid4(),
					book_id=book_id,
					version_number=1,
					source_draft_revision=1,
					content_json=published_content.model_dump(mode="json"),
					published_by=self.owner_id,
				)
			)

		async with self.sessions() as session:
			with_publication = await workspace_overview.get_workspace_overview(session, system_id)

		self.assertEqual(with_publication.books[0].latest_version, 1)
		self.assertIsNotNone(with_publication.books[0].latest_published_at)
		self.assertEqual(with_publication.books_published, 1)

		# 5. Публикация: версия механики и комплект системы.
		mechanic_version_id = uuid4()
		bundle_id = uuid4()

		async with self.sessions.begin() as session:
			await session.execute(
				insert(_MECHANIC_VERSIONS).values(
					id=mechanic_version_id,
					system_id=system_id,
					version_number=1,
					source_draft_revision=1,
					engine_version_id=engine_version_id,
					mechanic_overrides_json={"hp": 10},
					mechanic_json=MECHANIC_SNAPSHOT,
					rules_engine_version="1.0",
				)
			)
			await session.execute(
				insert(_SYSTEM_VERSIONS).values(
					id=bundle_id,
					system_id=system_id,
					version_number=1,
					text_version_id=None,
					mechanic_version_id=mechanic_version_id,
				)
			)

		async with self.sessions() as session:
			final = await workspace_overview.get_workspace_overview(session, system_id)

		self.assertTrue(final.rules_published)
		self.assertTrue(final.rules_draft_present)
		self.assertEqual(final.published_rules_version_id, bundle_id)
		self.assertEqual(final.books_published, 1)

		# 6. Read-only: обзор ничего не записывает (кроме явных вставок выше).
		after = await self.row_counts()
		self.assertEqual(after["systems"], before["systems"] + 0)
		self.assertEqual(after["drafts"], before["drafts"] + 1)
		self.assertEqual(after["books"], before["books"] + 1)
		self.assertEqual(after["book_versions"], before["book_versions"] + 1)

	async def test_missing_system_raises(self):
		async with self.sessions() as session:
			with self.assertRaises(GameSystemNotFound):
				await workspace_overview.get_workspace_overview(session, uuid4())


if __name__ == "__main__":
	unittest.main()
