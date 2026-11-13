# backend/app/modules/rules/services/catalog_service.py

"""Каталоги последних публикаций статей и книг.

Черновики не читаются.
Доступ проверяется до пагинации.
Транзакцией управляет вызывающий слой.
"""

from __future__ import annotations
from uuid import UUID
from sqlalchemy import Table, and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.modules.rules.models.articles import RuleArticle, RuleArticleVersion
from backend.app.modules.rules.models.books import RuleBook, RuleBookVersion, RuleBookVersionArticle
from backend.app.modules.rules.schemas.catalog import CatalogItem, CatalogPage, CatalogQuery
from backend.app.modules.game_systems.models.game_systems import GameSystem


_ARTICLES = RuleArticle.__table__
_ARTICLE_VERSIONS = RuleArticleVersion.__table__
_BOOKS = RuleBook.__table__
_BOOK_VERSIONS = RuleBookVersion.__table__
_DEPENDENCIES = RuleBookVersionArticle.__table__
_SYSTEMS = GameSystem.__table__

class InvalidCatalogQuery(ValueError):
	"""Некорректный контекст или фильтры каталога."""

class CatalogStorageError(RuntimeError):
	"""Сохранённые данные не соответствуют контракту каталога."""

def _prepare(session: AsyncSession, actor_id: UUID, query: CatalogQuery) -> CatalogQuery:
	if not isinstance(actor_id, UUID):
		raise InvalidCatalogQuery("Требуется идентификатор проверенного пользователя")

	if not isinstance(query, CatalogQuery):
		raise InvalidCatalogQuery("Передан неподдерживаемый контракт каталога")

	if session.new or session.dirty or session.deleted:
		raise RuntimeError("Каталог требует сессии без ожидающих ORM-изменений")

	if session.get_bind().dialect.name != "postgresql":
		raise RuntimeError("Каталог правил рассчитан на PostgreSQL")

	if not session.in_transaction():
		raise RuntimeError("Чтение каталога требует транзакцию вызывающего слоя")

	try:
		return CatalogQuery.model_validate(query.model_dump(mode="python"))
	except ValueError as exc:
		raise InvalidCatalogQuery("Фильтры каталога не прошли проверку") from exc

def _latest_statement(cards: Table, versions: Table, parent_field: str, actor_id: UUID):
	"""Соединить карточку исключительно с её последней публикацией."""
	content = versions.c.content_json
	parent = versions.c[parent_field]

	latest = (
		select(func.max(versions.c.version_number))
		.where(parent == cards.c.id)
		.correlate(cards)
		.scalar_subquery()
	)

	columns = [
		cards.c.id,
		cards.c.slug,
		cards.c.visibility,
		func.coalesce(cards.c.owner_id == actor_id, False).label("is_owned"),
		versions.c.id.label("version_id"),
		versions.c.version_number,
		versions.c.published_at,
		content["title"].astext.label("title"),
		func.coalesce(content["summary"].astext, "").label("summary"),
		content["edition_key"].astext.label("edition_key"),
		func.coalesce(content["language"].astext, "ru").label("language"),
	]

	return (
		select(*columns)
		.select_from(cards.join(versions, parent == cards.c.id))
		.where(cards.c.is_active.is_(True), versions.c.version_number == latest)
	)

def _filter_statement(statement, cards: Table, versions: Table, actor_id: UUID, query: CatalogQuery):
	own = cards.c.owner_id == actor_id
	public = cards.c.visibility == "public"
	content = versions.c.content_json

	statement = statement.where(own if query.scope == "mine" else or_(own, public))

	if query.after is not None:
		statement = statement.where(cards.c.id > query.after)

	if query.q is not None:
		title = content["title"].astext
		summary = func.coalesce(content["summary"].astext, "")
		statement = statement.where(or_(title.icontains(query.q, autoescape=True), summary.icontains(query.q, autoescape=True)))

	if query.edition_key is not None:
		statement = statement.where(content["edition_key"].astext == query.edition_key)

	if query.language is not None:
		statement = statement.where(func.coalesce(content["language"].astext, "ru") == query.language)

	return statement.order_by(cards.c.id).limit(query.limit + 1)

def _book_dependencies_allowed(actor_id: UUID):
	"""Запретить выдачу книги с отсутствующей или недоступной зависимостью."""
	dependencies = _DEPENDENCIES.alias("catalog_dependencies")
	versions = _ARTICLE_VERSIONS.alias("catalog_article_versions")
	articles = _ARTICLES.alias("catalog_articles")

	source = (
		dependencies
		.outerjoin(versions, versions.c.id == dependencies.c.article_version_id)
		.outerjoin(articles, articles.c.id == versions.c.article_id)
	)

	visible = or_(
		articles.c.visibility == "public",
		and_(_BOOKS.c.visibility == "private", articles.c.owner_id == actor_id),
		)
	allowed = and_(articles.c.is_active.is_(True), visible)

	unavailable = (
		select(1)
		.select_from(source)
		.where(dependencies.c.book_version_id == _BOOK_VERSIONS.c.id)
		.where(~func.coalesce(allowed, False))
		.correlate(_BOOKS, _BOOK_VERSIONS)
	)
	has_dependencies = (
		select(1)
		.select_from(dependencies)
		.where(dependencies.c.book_version_id == _BOOK_VERSIONS.c.id)
		.correlate(_BOOK_VERSIONS)
	)

	return and_(exists(has_dependencies), ~exists(unavailable))

async def _page(session: AsyncSession, statement, limit: int) -> CatalogPage:
	result = await session.execute(statement)
	rows = result.mappings().all()

	try:
		items = [CatalogItem.model_validate(dict(row)) for row in rows[:limit]]
	except ValueError as exc:
		raise CatalogStorageError("Сохранённые данные каталога имеют неподдерживаемый формат") from exc

	next_after = items[-1].id if len(rows) > limit else None

	return CatalogPage(items=items, next_after=next_after)

async def list_articles(session: AsyncSession, actor_id: UUID, query: CatalogQuery) -> CatalogPage:
	query = _prepare(session, actor_id, query)
	statement = _latest_statement(_ARTICLES, _ARTICLE_VERSIONS, "article_id", actor_id)
	statement = _filter_statement(statement, _ARTICLES, _ARTICLE_VERSIONS, actor_id, query)

	return await _page(session, statement, query.limit)

async def list_books(session: AsyncSession, actor_id: UUID, query: CatalogQuery, *, system_id: UUID | None = None) -> CatalogPage:
	query = _prepare(session, actor_id, query)

	if system_id is not None and not isinstance(system_id, UUID):
		raise InvalidCatalogQuery("Некорректный идентификатор игровой системы")

	active_system = (
		select(1)
		.select_from(_SYSTEMS)
		.where(_SYSTEMS.c.id == _BOOKS.c.system_id, _SYSTEMS.c.is_active.is_(True))
		.correlate(_BOOKS)
	)

	statement = _latest_statement(_BOOKS, _BOOK_VERSIONS, "book_id", actor_id)
	statement = statement.where(_book_dependencies_allowed(actor_id))
	statement = statement.where(or_(_BOOKS.c.system_id.is_(None), exists(active_system)))

	if system_id is not None:
		statement = statement.where(_BOOKS.c.system_id == system_id)

	statement = _filter_statement(statement, _BOOKS, _BOOK_VERSIONS, actor_id, query)
	return await _page(session, statement, query.limit)