# backend/app/modules/rules/services/article_service.py

"""Создание, сохранение и публикация самостоятельных статей.

actor_id передаётся из проверенной аутентификации, не из тела запроса.
Черновики доступны только владельцу.
Чужие публикации доступны у активной публичной статьи.

Право пользоваться редактором проверяет внешний прикладной слой.
Этот сервис дополнительно проверяет принадлежность конкретной статьи.

Транзакцией управляет вызывающий слой.
Сервис не выполняет commit или rollback.
После ошибки вызывающий слой должен откатить транзакцию.

Порядок блокировок: карточка статьи -> черновик.
Сервис использует Core-запросы и не смешивается с ожидающими ORM-изменениями.
"""

from __future__ import annotations
from backend.app.modules.rules.models.books import RuleBookText
from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID
from sqlalchemy import exists, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.modules.rules import errors
from backend.app.modules.rules.models.articles import RuleArticle, RuleArticleDraft, RuleArticleVersion
from backend.app.modules.rules.schemas import articles as contracts


_ARTICLES = RuleArticle.__table__
_DRAFTS = RuleArticleDraft.__table__
_VERSIONS = RuleArticleVersion.__table__
_BOOK_TEXTS = RuleBookText.__table__

ReadModel = TypeVar("ReadModel", bound=contracts.RulesContentModel)
DraftRead = contracts.RuleArticleDraftRead
EditorRead = contracts.RuleArticleEditorRead
PublishRead = contracts.RuleArticlePublishRead
VersionRead = contracts.RuleArticleVersionRead


def _prepare(session: AsyncSession, actor_id: UUID, *identifiers: UUID) -> None:
	"""Проверить контекст операции до выполнения запросов."""
	if not isinstance(actor_id, UUID):
		raise errors.InvalidRuleArticle("Требуется идентификатор проверенного пользователя")

	if any(not isinstance(identifier, UUID) for identifier in identifiers):
		raise errors.InvalidRuleArticle("Некорректный идентификатор статьи или публикации")

	if session.new or session.dirty or session.deleted:
		raise RuntimeError("Операция статьи требует сессии без ожидающих ORM-изменений")

	if session.get_bind().dialect.name != "postgresql":
		raise RuntimeError("Сервис статей рассчитан на PostgreSQL")


def _request(model: type[ReadModel], value: ReadModel) -> ReadModel:
	"""Повторно проверить контракт, в том числе после изменения его полей."""
	if not isinstance(value, model):
		raise errors.InvalidRuleArticle("Передан неподдерживаемый контракт операции")

	try:
		return model.model_validate(value.model_dump(mode="python"))
	except ValueError as exc:
		raise errors.InvalidRuleArticle("Данные статьи не прошли проверку") from exc


def _read(model: type[ReadModel], row: Mapping[str, Any]) -> ReadModel:
	"""Отделить повреждённые сохранённые данные от ошибок пользователя."""
	try:
		return model.model_validate(dict(row))
	except ValueError as exc:
		raise errors.RuleArticleStorageError("Сохранённые данные статьи имеют неподдерживаемый формат") from exc


def _check_revision(draft: Mapping[str, Any], expected_revision: int) -> None:
	if draft["revision"] != expected_revision:
		raise errors.RuleArticleConflict("Черновик уже изменён. Получите актуальную ревизию")


async def _article(session: AsyncSession, article_id: UUID, actor_id: UUID, *, owner_only: bool, write: bool):
	"""Заблокировать карточку и проверить доступ."""
	internal = (
		select(1)
		.select_from(_BOOK_TEXTS)
		.where(_BOOK_TEXTS.c.article_id == _ARTICLES.c.id)
		.correlate(_ARTICLES)
	)
	statement = (
		select(_ARTICLES)
		.where(_ARTICLES.c.id == article_id, ~exists(internal))
		.with_for_update(read=not write)
	)
	result = await session.execute(statement)
	row = result.mappings().one_or_none()

	if row is None:
		raise errors.RuleArticleNotFound("Статья не найдена")

	is_owner = row["owner_id"] == actor_id
	is_public = row["visibility"] == "public" and row["is_active"]

	if not is_owner and (owner_only or not is_public):
		raise errors.RuleArticleNotFound("Статья не найдена")

	return row


async def _draft(session: AsyncSession, article_id: UUID, *, write: bool):
	statement = (
		select(_DRAFTS)
		.where(_DRAFTS.c.article_id == article_id)
		.with_for_update(read=not write)
	)
	result = await session.execute(statement)
	row = result.mappings().one_or_none()

	if row is None:
		raise errors.RuleArticleStorageError("У статьи отсутствует обязательный черновик")

	return row


async def _save_draft(session: AsyncSession, draft: Mapping[str, Any], payload: dict | None = None) -> DraftRead:
	"""Увеличить ревизию с проверкой предыдущего значения."""
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
			_DRAFTS.c.article_id == draft["article_id"],
			_DRAFTS.c.revision == draft["revision"],
			)
		.values(**values)
		.returning(*_DRAFTS.c)
	)
	result = await session.execute(statement)
	row = result.mappings().one_or_none()

	if row is None:
		raise errors.RuleArticleConflict("Черновик изменился во время операции")

	return _read(DraftRead, row)


async def _touch_article(session: AsyncSession, article_id: UUID) -> None:
	statement = (
		update(_ARTICLES)
		.where(_ARTICLES.c.id == article_id)
		.values(updated_at=func.now())
	)
	await session.execute(statement)


async def create_article(session: AsyncSession, actor_id: UUID, data: contracts.RuleArticleCreate) -> EditorRead:
	"""Создать карточку и первый черновик в транзакции вызывающего слоя."""
	_prepare(session, actor_id)
	data = _request(contracts.RuleArticleCreate, data)
	payload = data.content.model_dump(mode="json")

	statement = (
		pg_insert(_ARTICLES)
		.values(
			owner_id=actor_id,
			slug=data.slug,
			visibility=data.visibility,
			is_active=True,
		)
		.on_conflict_do_nothing(constraint="uq_rule_articles_slug")
		.returning(*_ARTICLES.c)
	)
	result = await session.execute(statement)
	article = result.mappings().one_or_none()

	if article is None:
		raise errors.RuleArticleConflict("Этот код статьи уже занят")

	statement = (
		insert(_DRAFTS)
		.values(
			article_id=article["id"],
			content_json=payload,
			revision=1,
		)
		.returning(*_DRAFTS.c)
	)
	result = await session.execute(statement)
	draft = result.mappings().one()

	return EditorRead(
		article=_read(contracts.RuleArticleRead, article),
		draft=_read(DraftRead, draft),
	)


async def get_article_draft(session: AsyncSession, article_id: UUID, actor_id: UUID) -> DraftRead:
	"""Прочитать черновик только собственной статьи."""
	_prepare(session, actor_id, article_id)

	await _article(session, article_id, actor_id, owner_only=True, write=False)
	draft = await _draft(session, article_id, write=False)

	return _read(DraftRead, draft)


async def update_article_draft(session: AsyncSession, article_id: UUID, actor_id: UUID, data: contracts.RuleArticleDraftUpdate) -> DraftRead:
	"""Полностью заменить содержание черновика с проверкой ревизии."""
	_prepare(session, actor_id, article_id)
	data = _request(contracts.RuleArticleDraftUpdate, data)
	payload = data.content.model_dump(mode="json")

	await _article(session, article_id, actor_id, owner_only=True, write=True)
	draft = await _draft(session, article_id, write=True)

	_check_revision(draft, data.expected_revision)

	# Не перезаписываем неизвестный формат старым клиентом.
	_read(DraftRead, draft)

	saved = await _save_draft(session, draft, payload)
	await _touch_article(session, article_id)

	return saved


async def publish_article(session: AsyncSession, article_id: UUID, actor_id: UUID, data: contracts.RuleArticlePublish) -> PublishRead:
	"""Опубликовать сохранённый текст и увеличить ревизию черновика."""
	_prepare(session, actor_id, article_id)
	data = _request(contracts.RuleArticlePublish, data)

	article = await _article(session, article_id, actor_id, owner_only=True, write=True)

	if not article["is_active"]:
		raise errors.RuleArticleConflict("Перед публикацией активируйте статью")

	draft = await _draft(session, article_id, write=True)
	_check_revision(draft, data.expected_revision)

	checked = _read(DraftRead, draft)

	try:
		checked.content_json.ensure_publishable()
	except ValueError as exc:
		raise errors.RuleArticleConflict("Перед публикацией добавьте текст статьи") from exc

	statement = (
		select(func.coalesce(func.max(_VERSIONS.c.version_number), 0) + 1)
		.where(_VERSIONS.c.article_id == article_id)
	)
	result = await session.execute(statement)
	next_number = result.scalar_one()

	statement = (
		insert(_VERSIONS)
		.values(
			article_id=article_id,
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
	await _touch_article(session, article_id)

	return PublishRead(
		publication=publication,
		draft_revision=saved.revision,
	)


async def get_article_version(session: AsyncSession, article_id: UUID, version_id: UUID, actor_id: UUID) -> VersionRead:
	"""Прочитать конкретную публикацию с проверкой её принадлежности."""
	_prepare(session, actor_id, article_id, version_id)

	await _article(session, article_id, actor_id, owner_only=False, write=False)

	statement = select(_VERSIONS).where(
		_VERSIONS.c.id == version_id,
		_VERSIONS.c.article_id == article_id,
		)
	result = await session.execute(statement)
	publication = result.mappings().one_or_none()

	if publication is None:
		raise errors.RuleArticleNotFound("Публикация статьи не найдена")

	return _read(VersionRead, publication)
