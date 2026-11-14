# backend/app/modules/rules/services/books/book_authoring.py

"""Список собственных книг, включая неопубликованные черновики.

Транзакцией управляет вызывающий слой.
Права пользоваться авторским разделом проверяются на HTTP-границе.
Владелец книги дополнительно ограничивается самим SQL-запросом.
"""

from uuid import UUID
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.modules.rules import errors
from backend.app.modules.rules.models.books import RuleBook, RuleBookDraft, RuleBookVersion
from backend.app.modules.rules.schemas.books import book_authoring as contracts
from backend.app.modules.rules.schemas.books.books import BookContent
from backend.app.modules.rules.services.books.book_publication_state import book_content_changed, load_owned_snapshots


_BOOKS = RuleBook.__table__
_DRAFTS = RuleBookDraft.__table__
_VERSIONS = RuleBookVersion.__table__

def _prepare(session: AsyncSession, actor_id: UUID, query: contracts.AuthorBookQuery) -> contracts.AuthorBookQuery:
	if not isinstance(actor_id, UUID):
		raise errors.InvalidRuleBook("Требуется идентификатор проверенного пользователя")

	if not isinstance(query, contracts.AuthorBookQuery):
		raise errors.InvalidRuleBook("Передан неподдерживаемый контракт авторского каталога")

	if session.new or session.dirty or session.deleted:
		raise RuntimeError("Авторский каталог требует сессию без ожидающих ORM-изменений")

	if session.get_bind().dialect.name != "postgresql":
		raise RuntimeError("Авторский каталог рассчитан на PostgreSQL")

	if not session.in_transaction():
		raise RuntimeError("Авторский каталог требует транзакцию вызывающего слоя")

	try:
		return contracts.AuthorBookQuery.model_validate(query.model_dump(mode="python"))
	except ValueError as exc:
		raise errors.InvalidRuleBook("Фильтры авторского каталога не прошли проверку") from exc

def _statement(actor_id: UUID, query: contracts.AuthorBookQuery):
	content = _DRAFTS.c.content_json

	latest_number = (
		select(func.max(_VERSIONS.c.version_number))
		.where(_VERSIONS.c.book_id == _BOOKS.c.id)
		.correlate(_BOOKS)
		.scalar_subquery()
	)

	version_match = and_(
		_VERSIONS.c.book_id == _BOOKS.c.id,
		_VERSIONS.c.version_number == latest_number,
		)

	source = (
		_BOOKS
		.outerjoin(_DRAFTS, _DRAFTS.c.book_id == _BOOKS.c.id)
		.outerjoin(_VERSIONS, version_match)
	)

	statement = (
		select(
			_BOOKS.c.id,
			_BOOKS.c.slug,
			_BOOKS.c.system_id,
			_BOOKS.c.visibility,
			_BOOKS.c.is_active,
			content["title"].astext.label("title"),
			func.coalesce(content["summary"].astext, "").label("summary"),
			func.coalesce(content["language"].astext, "ru").label("language"),
			content["edition_key"].astext.label("edition_key"),
			_DRAFTS.c.revision.label("draft_revision"),
			_DRAFTS.c.updated_at.label("draft_updated_at"),
			_VERSIONS.c.id.label("version_id"),
			_VERSIONS.c.version_number,
			content.label("draft_content"),
			_VERSIONS.c.content_json.label("publication_content"),
		)
		.select_from(source)
		.where(_BOOKS.c.owner_id == actor_id)
	)

	if query.system_id is not None:
		statement = statement.where(_BOOKS.c.system_id == query.system_id)

	if query.after is not None:
		statement = statement.where(_BOOKS.c.id > query.after)

	if query.q is not None:
		title = content["title"].astext
		summary = func.coalesce(content["summary"].astext, "")
		matches = or_(title.icontains(query.q, autoescape=True), summary.icontains(query.q, autoescape=True))
		statement = statement.where(matches)

	if query.edition_key is not None:
		statement = statement.where(content["edition_key"].astext == query.edition_key)

	if query.language is not None:
		language = func.coalesce(content["language"].astext, "ru")
		statement = statement.where(language == query.language)

	return statement.order_by(_BOOKS.c.id).limit(query.limit + 1)

async def list_author_books(session: AsyncSession, actor_id: UUID, query: contracts.AuthorBookQuery) -> contracts.AuthorBookPage:
	query = _prepare(session, actor_id, query)
	result = await session.execute(_statement(actor_id, query))
	rows = result.mappings().all()
	visible = [dict(row) for row in rows[:query.limit]]

	try:
		publications = {}

		for row in visible:
			payload = row["publication_content"]

			if payload is not None:
				publications[row["id"]] = BookContent.model_validate(payload)

		snapshots = await load_owned_snapshots(session, list(publications.values()))
		items = []

		for row in visible:
			book_id = row["id"]
			draft = row.pop("draft_content")
			row.pop("publication_content")

			row["has_unpublished_changes"] = book_content_changed(
				book_id,
				draft,
				publications.get(book_id),
				snapshots,
			)
			items.append(contracts.AuthorBookItem.model_validate(row))
	except (KeyError, TypeError, ValueError) as exc:
		raise errors.RuleBookStorageError("Сохранённые данные авторского каталога имеют неподдерживаемый формат") from exc

	next_after = items[-1].id if len(rows) > query.limit else None

	return contracts.AuthorBookPage(items=items, next_after=next_after)