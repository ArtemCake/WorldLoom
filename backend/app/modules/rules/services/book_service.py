# backend/app/modules/rules/services/book_service.py

"""Операции с книгами правил и проверка закреплённых статей.

actor_id поступает из проверенной аутентификации.
Разрешение пользоваться редактором проверяет вызывающий слой.

Транзакцией управляет вызывающий слой.
Сервис требует активную транзакцию и не выполняет commit или rollback.
Исключение должно привести к откату всей операции.

Порядок блокировок:
карточка книги -> черновик -> карточки статей по идентификаторам.

Зависимости публикации создаёт PostgreSQL-триггер.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from sqlalchemy import func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.modules.rules import errors
from backend.app.modules.rules.models.articles import RuleArticle, RuleArticleVersion
from backend.app.modules.rules.models.books import RuleBook, RuleBookDraft, RuleBookVersion
from backend.app.modules.rules.schemas import books as contracts
from backend.app.modules.rules.schemas.articles import RulesContentModel


_BOOKS = RuleBook.__table__
_DRAFTS = RuleBookDraft.__table__
_VERSIONS = RuleBookVersion.__table__
_ARTICLES = RuleArticle.__table__
_ARTICLE_VERSIONS = RuleArticleVersion.__table__

ReadModel = TypeVar("ReadModel", bound=RulesContentModel)

BookContent = contracts.BookContent
BookCreate = contracts.RuleBookCreate
BookUpdate = contracts.RuleBookDraftUpdate
BookPublish = contracts.RuleBookPublish
DraftRead = contracts.RuleBookDraftRead
EditorRead = contracts.RuleBookEditorRead
PublishRead = contracts.RuleBookPublishRead
VersionRead = contracts.RuleBookVersionRead


def _prepare(session: AsyncSession, actor_id: UUID, *identifiers: UUID) -> None:
	if not isinstance(actor_id, UUID):
		raise errors.InvalidRuleBook("Требуется идентификатор проверенного пользователя")

	if any(not isinstance(identifier, UUID) for identifier in identifiers):
		raise errors.InvalidRuleBook("Некорректный идентификатор книги или публикации")

	if session.new or session.dirty or session.deleted:
		raise RuntimeError("Операция книги требует сессии без ожидающих ORM-изменений")

	if session.get_bind().dialect.name != "postgresql":
		raise RuntimeError("Сервис книг рассчитан на PostgreSQL")

	if not session.in_transaction():
		raise RuntimeError("Операция книги требует транзакцию вызывающего слоя")


def _request(model: type[ReadModel], value: ReadModel) -> ReadModel:
	if not isinstance(value, model):
		raise errors.InvalidRuleBook("Передан неподдерживаемый контракт операции")

	try:
		return model.model_validate(value.model_dump(mode="python"))
	except ValueError as exc:
		raise errors.InvalidRuleBook("Данные книги не прошли проверку") from exc


def _read(model: type[ReadModel], row: Mapping[str, Any]) -> ReadModel:
	try:
		return model.model_validate(dict(row))
	except ValueError as exc:
		raise errors.RuleBookStorageError("Сохранённые данные книги имеют неподдерживаемый формат") from exc


def _check_revision(draft: Mapping[str, Any], expected_revision: int) -> None:
	if draft["revision"] != expected_revision:
		raise errors.RuleBookConflict("Черновик книги уже изменён. Получите актуальную ревизию")


async def _book(session: AsyncSession, book_id: UUID, actor_id: UUID, *, owner_only: bool, write: bool):
	statement = (
		select(_BOOKS)
		.where(_BOOKS.c.id == book_id)
		.with_for_update(read=not write)
	)
	result = await session.execute(statement)
	row = result.mappings().one_or_none()

	if row is None:
		raise errors.RuleBookNotFound("Книга не найдена")

	is_owner = row["owner_id"] == actor_id
	is_public = row["visibility"] == "public" and row["is_active"]

	if not is_owner and (owner_only or not is_public):
		raise errors.RuleBookNotFound("Книга не найдена")

	return row


async def _draft(session: AsyncSession, book_id: UUID, *, write: bool):
	statement = (
		select(_DRAFTS)
		.where(_DRAFTS.c.book_id == book_id)
		.with_for_update(read=not write)
	)
	result = await session.execute(statement)
	row = result.mappings().one_or_none()

	if row is None:
		raise errors.RuleBookStorageError("У книги отсутствует обязательный черновик")

	return row


async def _dependencies(session: AsyncSession, content: BookContent, actor_id: UUID, *, public_only: bool) -> None:
	"""Проверить все публикации и удержать карточки статей до конца транзакции."""
	identifiers = content.article_version_ids()

	if not identifiers:
		return

	statement = (
		select(
			_ARTICLE_VERSIONS.c.id.label("version_id"),
			_ARTICLES.c.owner_id,
			_ARTICLES.c.visibility,
			_ARTICLES.c.is_active,
		)
		.select_from(_ARTICLE_VERSIONS.join(_ARTICLES, _ARTICLE_VERSIONS.c.article_id == _ARTICLES.c.id))
		.where(_ARTICLE_VERSIONS.c.id.in_(identifiers))
		.order_by(_ARTICLES.c.id, _ARTICLE_VERSIONS.c.id)
		.with_for_update(read=True, of=_ARTICLES)
	)
	result = await session.execute(statement)
	rows = result.mappings().all()

	if {row["version_id"] for row in rows} != set(identifiers):
		raise errors.RuleBookDependencyUnavailable("Некоторые публикации статей отсутствуют или недоступны")

	for row in rows:
		is_public = row["visibility"] == "public"
		is_owner = row["owner_id"] == actor_id
		allowed = is_public if public_only else is_public or is_owner

		if not row["is_active"] or not allowed:
			raise errors.RuleBookDependencyUnavailable("Некоторые публикации статей отсутствуют или недоступны")


async def _save_draft(session: AsyncSession, draft: Mapping[str, Any], payload: dict | None = None) -> DraftRead:
	values = {
		"revision": _DRAFTS.c.revision + 1,
		"updated_at": func.now(),
	}

	if payload is not None:
		values["content_json"] = payload

	statement = (
		update(_DRAFTS)
		.where(
			_DRAFTS.c.id == draft["id"],
			_DRAFTS.c.book_id == draft["book_id"],
			_DRAFTS.c.revision == draft["revision"],
			)
		.values(**values)
		.returning(*_DRAFTS.c)
	)
	result = await session.execute(statement)
	row = result.mappings().one_or_none()

	if row is None:
		raise errors.RuleBookConflict("Черновик книги изменился во время операции")

	return _read(DraftRead, row)


async def _touch_book(session: AsyncSession, book_id: UUID) -> None:
	statement = update(_BOOKS).where(_BOOKS.c.id == book_id).values(updated_at=func.now())
	await session.execute(statement)


async def create_book(session: AsyncSession, actor_id: UUID, data: BookCreate) -> EditorRead:
	"""Создать карточку и черновик; пустое оглавление разрешено."""
	_prepare(session, actor_id)
	data = _request(BookCreate, data)

	# Черновик публичной книги остаётся приватным.
	# Строгое требование публичных источников применяется при публикации.
	await _dependencies(session, data.content, actor_id, public_only=False)

	statement = (
		pg_insert(_BOOKS)
		.values(
			owner_id=actor_id,
			slug=data.slug,
			visibility=data.visibility,
			is_active=True,
		)
		.on_conflict_do_nothing(constraint="uq_rule_books_slug")
		.returning(*_BOOKS.c)
	)
	result = await session.execute(statement)
	book = result.mappings().one_or_none()

	if book is None:
		raise errors.RuleBookConflict("Этот код книги уже занят")

	statement = (
		insert(_DRAFTS)
		.values(
			book_id=book["id"],
			revision=1,
			content_json=data.content.model_dump(mode="json"),
		)
		.returning(*_DRAFTS.c)
	)
	result = await session.execute(statement)
	draft = result.mappings().one()

	return EditorRead(
		book=_read(contracts.RuleBookRead, book),
		draft=_read(DraftRead, draft),
	)


async def get_book_draft(session: AsyncSession, book_id: UUID, actor_id: UUID) -> DraftRead:
	"""Владелец может открыть черновик и исправить недоступные ссылки."""
	_prepare(session, actor_id, book_id)

	await _book(session, book_id, actor_id, owner_only=True, write=False)
	draft = await _draft(session, book_id, write=False)

	return _read(DraftRead, draft)


async def update_book_draft(session: AsyncSession, book_id: UUID, actor_id: UUID, data: BookUpdate) -> DraftRead:
	"""Сохранить полное содержание с проверкой структуры, ссылок и ревизии."""
	_prepare(session, actor_id, book_id)
	data = _request(BookUpdate, data)

	await _book(session, book_id, actor_id, owner_only=True, write=True)
	draft = await _draft(session, book_id, write=True)

	_check_revision(draft, data.expected_revision)
	_read(DraftRead, draft)

	await _dependencies(session, data.content, actor_id, public_only=False)

	saved = await _save_draft(session, draft, data.content.model_dump(mode="json"))
	await _touch_book(session, book_id)

	return saved


async def publish_book(session: AsyncSession, book_id: UUID, actor_id: UUID, data: BookPublish) -> PublishRead:
	"""Выпустить снимок сохранённого черновика и увеличить его ревизию."""
	_prepare(session, actor_id, book_id)
	data = _request(BookPublish, data)

	book = await _book(session, book_id, actor_id, owner_only=True, write=True)

	if not book["is_active"]:
		raise errors.RuleBookConflict("Перед публикацией активируйте книгу")

	draft = await _draft(session, book_id, write=True)
	_check_revision(draft, data.expected_revision)
	checked = _read(DraftRead, draft)

	try:
		checked.content_json.ensure_publishable()
	except ValueError as exc:
		raise errors.RuleBookConflict("Для публикации книги требуется корректное оглавление со статьями") from exc

	await _dependencies(
		session,
		checked.content_json,
		actor_id,
		public_only=book["visibility"] == "public",
	)

	statement = (
		select(func.coalesce(func.max(_VERSIONS.c.version_number), 0) + 1)
		.where(_VERSIONS.c.book_id == book_id)
	)
	result = await session.execute(statement)
	next_number = result.scalar_one()

	statement = (
		insert(_VERSIONS)
		.values(
			book_id=book_id,
			version_number=next_number,
			source_draft_revision=draft["revision"],
			content_json=checked.content_json.model_dump(mode="json"),
			published_by=actor_id,
		)
		.returning(*_VERSIONS.c)
	)
	result = await session.execute(statement)
	publication = _read(VersionRead, result.mappings().one())

	saved = await _save_draft(session, draft)
	await _touch_book(session, book_id)

	return PublishRead(publication=publication, draft_revision=saved.revision)


async def get_book_version(session: AsyncSession, book_id: UUID, version_id: UUID, actor_id: UUID) -> VersionRead:
	"""Прочитать снимок без обхода текущих прав на исходные статьи."""
	_prepare(session, actor_id, book_id, version_id)

	book = await _book(session, book_id, actor_id, owner_only=False, write=False)

	statement = select(_VERSIONS).where(
		_VERSIONS.c.id == version_id,
		_VERSIONS.c.book_id == book_id,
		)
	result = await session.execute(statement)
	row = result.mappings().one_or_none()

	if row is None:
		raise errors.RuleBookNotFound("Публикация книги не найдена")

	publication = _read(VersionRead, row)

	try:
		await _dependencies(
			session,
			publication.content_json,
			actor_id,
			public_only=book["visibility"] == "public",
		)
	except errors.RuleBookDependencyUnavailable as exc:
		raise errors.RuleBookNotFound("Публикация книги недоступна") from exc

	return publication
