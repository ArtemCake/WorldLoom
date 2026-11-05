# backend/app/modules/game_systems/services/rule_engine_service.py

"""Управление переиспользуемыми основами пользовательских правил.

actor_id поступает от проверенной аутентификации, не из тела запроса.
Изменять основу и читать её черновик может только владелец.
Чужую публикацию можно читать у активной публичной основы.

Сервис не выполняет commit или rollback.
Вызывающий слой завершает транзакцию при любом исходе операции.
После ошибки изменяющей операции обязателен rollback.

Операции выполняются в сессии без посторонних ожидающих ORM-изменений.
Порядок блокировок: карточка основы -> черновик.
Опубликованные строки этим сервисом не изменяются и не удаляются.
"""

from __future__ import annotations
from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID
from sqlalchemy import delete, func, insert, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.modules.game_systems.errors import (GameSystemNotFound, GameSystemRulesConflict, GameSystemRulesStorageError, InvalidGameSystemRules)
from backend.app.modules.game_systems.models.rule_engines import RuleEngine, RuleEngineDraft, RuleEngineVersion
from backend.app.modules.game_systems.rules.rules_engine import validate_rules_profile
from backend.app.modules.game_systems.schemas.game_rules import RulesModel, RulesProfile
from backend.app.modules.game_systems.schemas.rules.rule_engines import (RuleEngineActivityUpdate, RuleEngineCreate, RuleEngineDelete, RuleEngineDeleteRead, RuleEngineDraftRead,
                                                                         RuleEngineDraftUpdate, RuleEngineEditorRead, RuleEnginePage, RuleEnginePublish, RuleEngineRead, RuleEngineVersionPage, RuleEngineVersionRead, RuleEngineVersionSummary)


_ENGINES = RuleEngine.__table__
_DRAFTS = RuleEngineDraft.__table__
_VERSIONS = RuleEngineVersion.__table__

ReadModel = TypeVar("ReadModel", bound=RulesModel)

def _prepare(session: AsyncSession, actor_id: UUID) -> None:
	"""Проверить идентификатор участника и чистоту ORM-сессии."""
	if not isinstance(actor_id, UUID):
		raise InvalidGameSystemRules("Требуется идентификатор проверенного пользователя")

	if session.new or session.dirty or session.deleted:
		raise RuntimeError("Операция основы требует сессии без ожидающих ORM-изменений")

def _payload(value: RulesProfile | Mapping[str, Any]) -> dict[str, Any]:
	"""Повторно проверить профиль и его начальное состояние."""
	if isinstance(value, RulesProfile):
		raw = value.model_dump(mode="python")
	elif isinstance(value, Mapping):
		raw = dict(value)
	else:
		raise ValueError("Профиль правил должен быть объектом")

	profile = RulesProfile.model_validate(raw)
	profile = validate_rules_profile(profile)

	return profile.model_dump(mode="json")

def _incoming_payload(profile: RulesProfile) -> dict[str, Any]:
	try:
		return _payload(profile)
	except ValueError as exc:
		raise InvalidGameSystemRules("Профиль основы или его начальное состояние недопустимы") from exc

def _read(model: type[ReadModel], row: Mapping[str, Any]) -> ReadModel:
	"""Не выдавать ошибку сохранённых данных за ошибку запроса."""
	try:
		return model.model_validate(dict(row))
	except ValueError as exc:
		raise GameSystemRulesStorageError("Сохранённые данные основы имеют неподдерживаемый формат") from exc

def _check_revision(draft: Mapping[str, Any], expected_revision: int) -> None:
	if draft["revision"] != expected_revision:
		raise GameSystemRulesConflict("Черновик основы уже изменён. Получите актуальную ревизию")

def _check_page(limit: int, offset: int) -> None:
	"""Ограничить размер страницы и отклонить нецелые значения."""
	if type(limit) is not int or type(offset) is not int:
		raise InvalidGameSystemRules("Размер страницы и смещение должны быть целыми числами")

	if not 1 <= limit <= 100 or offset < 0:
		raise InvalidGameSystemRules("Некорректные параметры страницы")

async def _find_engine(session: AsyncSession, engine_id: UUID, actor_id: UUID, *, owner_only: bool, write: bool) -> Mapping[str, Any]:
	result = await session.execute(
		select(_ENGINES)
		.where(_ENGINES.c.id == engine_id)
		.with_for_update(read=not write)
	)
	engine = result.mappings().one_or_none()

	if engine is None:
		raise GameSystemNotFound("Основа правил не найдена")

	is_owner = engine["owner_id"] == actor_id
	is_public = engine["visibility"] == "public" and engine["is_active"]

	if not is_owner and (owner_only or not is_public):
		raise GameSystemNotFound("Основа правил не найдена")

	return engine

async def _find_draft(session: AsyncSession, engine_id: UUID, *, write: bool) -> Mapping[str, Any]:
	result = await session.execute(
		select(_DRAFTS)
		.where(_DRAFTS.c.engine_id == engine_id)
		.with_for_update(read=not write)
	)
	draft = result.mappings().one_or_none()

	if draft is None:
		raise GameSystemNotFound("Черновик основы не найден")

	return draft

async def create_engine_with_draft(session: AsyncSession, actor_id: UUID, data: RuleEngineCreate) -> RuleEngineEditorRead:
	"""Создать собственную основу и её первый черновик."""
	_prepare(session, actor_id)
	data = RuleEngineCreate.model_validate(data.model_dump(mode="python"))
	payload = _incoming_payload(data.rules)

	engine_result = await session.execute(
		insert(_ENGINES)
		.values(
			owner_id=actor_id,
			name=data.name,
			slug=data.slug,
			description=data.description,
			visibility=data.visibility,
			is_active=True,
		)
		.returning(*_ENGINES.c)
	)
	engine = engine_result.mappings().one()

	draft_result = await session.execute(
		insert(_DRAFTS)
		.values(
			engine_id=engine["id"],
			rules_json=payload,
			rules_engine_version=data.rules_engine_version,
			revision=1,
		)
		.returning(*_DRAFTS.c)
	)
	draft = draft_result.mappings().one()

	return RuleEngineEditorRead(
		engine=_read(RuleEngineRead, engine),
		draft=_read(RuleEngineDraftRead, draft),
	)

async def get_engine_draft(session: AsyncSession, engine_id: UUID, actor_id: UUID) -> RuleEngineDraftRead:
	"""Прочитать черновик только собственной основы."""
	_prepare(session, actor_id)

	await _find_engine(session, engine_id, actor_id, owner_only=True, write=False)
	draft = await _find_draft(session, engine_id, write=False)

	return _read(RuleEngineDraftRead, draft)

def _check_profile_replacement(current: Mapping[str, Any], incoming: Mapping[str, Any]) -> None:
	"""Не позволять старому клиенту заменить новый профиль старым."""

	try:
		previous = RulesProfile.model_validate(dict(current))
	except ValueError as exc:
		raise GameSystemRulesStorageError("Сохранённый профиль основы имеет неподдерживаемый формат") from exc

	if incoming["schema_version"] < previous.schema_version:
		raise GameSystemRulesConflict("Понижение версии профиля запрещено. Откройте игровую систему в редакторе новой версии")

async def update_engine_draft(session: AsyncSession, engine_id: UUID, actor_id: UUID, data: RuleEngineDraftUpdate) -> RuleEngineDraftRead:
	"""Сохранить полный профиль без изменения версии исполнителя."""
	_prepare(session, actor_id)
	data = RuleEngineDraftUpdate.model_validate(data.model_dump(mode="python"))
	payload = _incoming_payload(data.rules)

	await _find_engine(session, engine_id, actor_id, owner_only=True, write=True)
	draft = await _find_draft(session, engine_id, write=True)
	_check_revision(draft, data.expected_revision)
	_check_profile_replacement(draft["rules_json"], payload)

	result = await session.execute(
		update(_DRAFTS)
		.where(
			_DRAFTS.c.id == draft["id"],
			_DRAFTS.c.revision == data.expected_revision,
			)
		.values(
			rules_json=payload,
			revision=_DRAFTS.c.revision + 1,
			updated_at=func.now(),
		)
		.returning(*_DRAFTS.c)
	)
	saved = result.mappings().one_or_none()

	if saved is None:
		raise GameSystemRulesConflict("Черновик основы изменился во время сохранения")

	return _read(RuleEngineDraftRead, saved)

async def publish_engine_version(session: AsyncSession, engine_id: UUID, actor_id: UUID, data: RuleEnginePublish) -> RuleEngineVersionRead:
	"""Опубликовать сохранённый черновик и потребить его ревизию."""
	_prepare(session, actor_id)
	data = RuleEnginePublish.model_validate(data.model_dump(mode="python"))

	engine = await _find_engine(session, engine_id, actor_id, owner_only=True, write=True)

	if not engine["is_active"]:
		raise GameSystemRulesConflict("Перед публикацией активируйте основу правил")

	draft = await _find_draft(session, engine_id, write=True)
	_check_revision(draft, data.expected_revision)

	try:
		payload = _payload(draft["rules_json"])
	except ValueError as exc:
		raise GameSystemRulesConflict("Сохранённый черновик основы не проходит проверку правил") from exc

	number_result = await session.execute(
		select(func.coalesce(func.max(_VERSIONS.c.version_number), 0) + 1)
		.where(_VERSIONS.c.engine_id == engine_id)
	)
	next_number = number_result.scalar_one()

	version_result = await session.execute(
		insert(_VERSIONS)
		.values(
			engine_id=engine_id,
			version_number=next_number,
			source_draft_revision=draft["revision"],
			rules_json=payload,
			rules_engine_version=draft["rules_engine_version"],
		)
		.returning(*_VERSIONS.c)
	)
	response = _read(RuleEngineVersionRead, version_result.mappings().one())

	revision_result = await session.execute(
		update(_DRAFTS)
		.where(
			_DRAFTS.c.id == draft["id"],
			_DRAFTS.c.revision == data.expected_revision,
			)
		.values(
			revision=_DRAFTS.c.revision + 1,
			updated_at=func.now(),
		)
		.returning(_DRAFTS.c.revision)
	)

	if revision_result.scalar_one_or_none() is None:
		raise GameSystemRulesConflict("Черновик основы изменился во время публикации")

	return response

async def get_engine_version(session: AsyncSession, engine_id: UUID, version_id: UUID, actor_id: UUID) -> RuleEngineVersionRead:
	"""Прочитать конкретную публикацию доступной основы."""
	_prepare(session, actor_id)

	await _find_engine(session, engine_id, actor_id, owner_only=False, write=False)

	result = await session.execute(
		select(_VERSIONS)
		.where(
			_VERSIONS.c.id == version_id,
			_VERSIONS.c.engine_id == engine_id,
			)
	)
	version = result.mappings().one_or_none()

	if version is None:
		raise GameSystemNotFound("Публикация основы не найдена")

	return _read(RuleEngineVersionRead, version)

async def list_rule_engines(session: AsyncSession, actor_id: UUID, *, owned_only: bool = False, limit: int = 50, offset: int = 0) -> RuleEnginePage:
	"""Прочитать собственные основы либо доступные основы для выбора."""
	_prepare(session, actor_id)
	_check_page(limit, offset)

	if type(owned_only) is not bool:
		raise InvalidGameSystemRules("Признак выбора собственных основ должен быть логическим")

	statement = select(_ENGINES)

	if owned_only:
		statement = statement.where(_ENGINES.c.owner_id == actor_id)
	else:
		has_publication = (
			select(_VERSIONS.c.id)
			.where(_VERSIONS.c.engine_id == _ENGINES.c.id)
			.exists()
		)
		statement = statement.where(
			_ENGINES.c.is_active.is_(True),
			or_(
				_ENGINES.c.owner_id == actor_id,
				_ENGINES.c.visibility == "public",
				),
			has_publication,
		)

	result = await session.execute(
		statement
		.order_by(_ENGINES.c.slug, _ENGINES.c.id)
		.offset(offset)
		.limit(limit + 1)
	)
	rows = list(result.mappings().all())

	return RuleEnginePage(
		items=[_read(RuleEngineRead, row) for row in rows[:limit]],
		next_offset=offset + limit if len(rows) > limit else None,
	)

async def list_engine_versions(session: AsyncSession, engine_id: UUID, actor_id: UUID, *, limit: int = 50, offset: int = 0) -> RuleEngineVersionPage:
	"""Прочитать страницу публикаций без полных профилей правил."""
	_prepare(session, actor_id)
	_check_page(limit, offset)

	await _find_engine(session, engine_id, actor_id, owner_only=False, write=False)

	result = await session.execute(
		select(
			_VERSIONS.c.id,
			_VERSIONS.c.engine_id,
			_VERSIONS.c.version_number,
			_VERSIONS.c.source_draft_revision,
			_VERSIONS.c.rules_engine_version,
			_VERSIONS.c.published_at,
		)
		.where(_VERSIONS.c.engine_id == engine_id)
		.order_by(_VERSIONS.c.version_number.desc())
		.offset(offset)
		.limit(limit + 1)
	)
	rows = list(result.mappings().all())

	return RuleEngineVersionPage(
		items=[_read(RuleEngineVersionSummary, row) for row in rows[:limit]],
		next_offset=offset + limit if len(rows) > limit else None,
	)

async def set_engine_activity(session: AsyncSession, engine_id: UUID, actor_id: UUID, data: RuleEngineActivityUpdate) -> RuleEngineRead:
	"""Изменить активность собственной основы без изменения правил."""
	_prepare(session, actor_id)
	data = RuleEngineActivityUpdate.model_validate(data.model_dump(mode="python"))

	engine = await _find_engine(session, engine_id, actor_id, owner_only=True, write=True)

	if engine["is_active"] != data.expected_is_active:
		raise GameSystemRulesConflict("Активность основы уже изменилась. Получите актуальное состояние")

	result = await session.execute(
		update(_ENGINES)
		.where(
			_ENGINES.c.id == engine_id,
			_ENGINES.c.is_active == data.expected_is_active,
			)
		.values(
			is_active=data.is_active,
			updated_at=func.now(),
		)
		.returning(*_ENGINES.c)
	)
	saved = result.mappings().one_or_none()

	if saved is None:
		raise GameSystemRulesConflict("Основа изменилась во время изменения активности")

	return _read(RuleEngineRead, saved)

async def delete_unpublished_engine(session: AsyncSession, engine_id: UUID, actor_id: UUID, data: RuleEngineDelete) -> RuleEngineDeleteRead:
	"""Удалить собственную основу, если у неё нет публикаций.

	Блокируем карточку, затем черновик и проверяем его ревизию.
	Удаление черновика возлагается на внешний ключ ON DELETE CASCADE.
	Публикации защищаются проверкой и внешним ключом ON DELETE RESTRICT.

	Если БД отклоняет удаление из-за связей, преобразуем ошибку
	в предметный конфликт. Транзакцию всё равно отменяет внешний слой.
	"""
	_prepare(session, actor_id)
	data = RuleEngineDelete.model_validate(data.model_dump(mode="python"))

	await _find_engine(session, engine_id, actor_id, owner_only=True, write=True)
	draft = await _find_draft(session, engine_id, write=True)
	_check_revision(draft, data.expected_revision)

	publication_result = await session.execute(
		select(
			select(_VERSIONS.c.id)
			.where(_VERSIONS.c.engine_id == engine_id)
			.exists()
		)
	)

	if publication_result.scalar_one():
		raise GameSystemRulesConflict("У основы есть публикации. Удаление запрещено; используйте деактивацию")

	try:
		deleted_result = await session.execute(
			delete(_ENGINES)
			.where(_ENGINES.c.id == engine_id)
			.returning(_ENGINES.c.id)
		)
	except IntegrityError as exc:
		sqlstate = getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)

		if sqlstate == "23503":
			raise GameSystemRulesConflict("Основа связана с другими данными. Удаление отменено; используйте деактивацию") from exc

		raise

	if deleted_result.scalar_one_or_none() != engine_id:
		raise GameSystemRulesConflict("Удаление основы не подтверждено. Получите актуальное состояние")

	return RuleEngineDeleteRead(deleted=True, engine_id=engine_id)