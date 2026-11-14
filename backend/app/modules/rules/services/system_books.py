# backend/app/modules/rules/services/system_books.py

"""Книги выбранной системы и переход ранее созданных книг."""

# backend/app/modules/rules/imports.py

from uuid import UUID
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.modules.game_systems.models.game_systems import GameSystem
from backend.app.modules.rules import errors
from backend.app.modules.rules.models.books import RuleBook, RuleBookDraft
from backend.app.modules.rules.schemas.books import books as book_contracts
from backend.app.modules.rules.schemas import system_books as contracts
from backend.app.modules.rules.services.books import book_service

_SYSTEMS = GameSystem.__table__
_BOOKS = RuleBook.__table__
_DRAFTS = RuleBookDraft.__table__

def _prepare(session: AsyncSession, actor_id: UUID, *identifiers: UUID) -> None:
	if not isinstance(actor_id, UUID):
		raise errors.InvalidRuleBook("Требуется идентификатор проверенного пользователя")

	if any(not isinstance(value, UUID) for value in identifiers):
		raise errors.InvalidRuleBook("Некорректный идентификатор книги или системы")

	if session.new or session.dirty or session.deleted:
		raise RuntimeError("Операция требует сессии без ожидающих ORM-изменений")

	if session.get_bind().dialect.name != "postgresql":
		raise RuntimeError("Операции книг рассчитаны на PostgreSQL")

	if not session.in_transaction():
		raise RuntimeError("Операция требует транзакцию вызывающего слоя")

def _request(model, data):
	if not isinstance(data, model):
		raise errors.InvalidRuleBook("Передан неподдерживаемый контракт операции")

	try:
		return model.model_validate(data.model_dump(mode="python"))
	except ValueError as exc:
		raise errors.InvalidRuleBook("Данные операции не прошли проверку") from exc

async def _active_system(session: AsyncSession, system_id: UUID) -> None:
	statement = (
		select(_SYSTEMS.c.id)
		.where(_SYSTEMS.c.id == system_id, _SYSTEMS.c.is_active.is_(True))
		.with_for_update(read=True)
	)
	found = (await session.execute(statement)).scalar_one_or_none()

	if found is None:
		raise errors.RuleBookNotFound("Игровая система недоступна")

async def _owned_book(session: AsyncSession, book_id: UUID, actor_id: UUID):
	statement = (
		select(_BOOKS)
		.where(
			_BOOKS.c.id == book_id,
			_BOOKS.c.owner_id == actor_id,
			_BOOKS.c.is_active.is_(True),
			)
		.with_for_update()
	)
	row = (await session.execute(statement)).mappings().one_or_none()

	if row is None:
		raise errors.RuleBookNotFound("Книга недоступна")

	return row

async def _locked_draft(session: AsyncSession, book_id: UUID):
	statement = select(_DRAFTS).where(_DRAFTS.c.book_id == book_id).with_for_update()
	row = (await session.execute(statement)).mappings().one_or_none()

	if row is None:
		raise errors.RuleBookStorageError("У книги отсутствует обязательный черновик")

	return row

async def create_system_book(session: AsyncSession, actor_id: UUID, data: contracts.SystemBookCreate):
	"""Создать книгу и назначить систему в одной внешней транзакции."""
	_prepare(session, actor_id)
	data = _request(contracts.SystemBookCreate, data)

	await _active_system(session, data.system_id)

	payload = data.model_dump(mode="python", exclude={"system_id"})
	request = book_contracts.RuleBookCreate.model_validate(payload)
	created = await book_service.create_book(session, actor_id, request)

	statement = (
		update(_BOOKS)
		.where(_BOOKS.c.id == created.book.id, _BOOKS.c.system_id.is_(None))
		.values(system_id=data.system_id, updated_at=func.now())
		.returning(*_BOOKS.c)
	)
	row = (await session.execute(statement)).mappings().one_or_none()

	if row is None:
		raise errors.RuleBookConflict("Не удалось назначить систему создаваемой книге")

	book = book_contracts.RuleBookRead.model_validate(dict(row))
	return book_contracts.RuleBookEditorRead(book=book, draft=created.draft)

async def assign_book_system(session: AsyncSession, book_id: UUID, actor_id: UUID, data: contracts.BookSystemAssign):
	"""Назначить систему старой книге без изменения опубликованного текста."""
	_prepare(session, actor_id, book_id)
	data = _request(contracts.BookSystemAssign, data)

	await _active_system(session, data.system_id)
	book = await _owned_book(session, book_id, actor_id)
	draft = await _locked_draft(session, book_id)

	if draft["revision"] != data.expected_revision:
		raise errors.RuleBookConflict("Книга уже изменена. Получите актуальную ревизию")

	if book["system_id"] is not None:
		raise errors.RuleBookConflict("Система книги уже назначена")

	await session.execute(
		update(_BOOKS)
		.where(_BOOKS.c.id == book_id)
		.values(system_id=data.system_id, updated_at=func.now())
	)

	statement = (
		update(_DRAFTS)
		.where(_DRAFTS.c.book_id == book_id, _DRAFTS.c.revision == data.expected_revision)
		.values(revision=_DRAFTS.c.revision + 1, updated_at=func.now())
		.returning(_DRAFTS.c.revision)
	)
	revision = (await session.execute(statement)).scalar_one_or_none()

	if revision is None:
		raise errors.RuleBookConflict("Черновик изменился во время назначения системы")

	return contracts.BookSystemAssignmentRead(book_id=book_id, system_id=data.system_id, draft_revision=revision)