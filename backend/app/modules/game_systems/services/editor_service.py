# backend/app/modules/game_systems/services/editor_service.py

"""Черновики и публикации правил существующих игровых систем.

Изменяющие операции вызываются после внешней проверки
права управления контентом.

Сервис не выполняет commit или rollback.
Транзакцию завершает вызывающий слой.

Порядок блокировок при изменении:
система -> черновик -> карточка новой основы, если нужна.

Опубликованные строки этим сервисом не изменяются.
"""

from __future__ import annotations
from collections.abc import Mapping
from typing import Any
from uuid import UUID
from sqlalchemy import func, insert, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.modules.game_systems.errors import (GameSystemNotFound, GameSystemRulesConflict, GameSystemRulesStorageError, InvalidGameSystemRules)
from backend.app.modules.game_systems.models.game_systems import (GameSystem, GameSystemRulesDraft, GameSystemRulesVersion)
from backend.app.modules.game_systems.rules.rules_engine import (validate_rules_profile)
from backend.app.modules.game_systems.schemas.game_rules import (GameSystemRulesDraftCreate, GameSystemRulesDraftRead, GameSystemRulesDraftState, GameSystemRulesDraftUpdate,
	GameSystemRulesPublish, GameSystemRulesVersionRead, RulesProfile)
from backend.app.modules.game_systems.schemas.game_system_origin import (EngineRulesSource, GameSystemDraftEngineSet, GameSystemEngineEditorUpdate,
    GameSystemEngineOriginRead, GameSystemFromEngineCreate)
from backend.app.modules.game_systems.services.system_rule_origin import (load_editor_engine_origin, load_engine_origin, load_saved_engine_version,
    origin_for_publication)
from backend.app.modules.catalog.schemas import GameSystemAdminRead, GameSystemCreate
from backend.app.modules.game_systems.schemas.game_system_editor import GameSystemEditorCreate, GameSystemEditorRead, GameSystemEditorUpdate
from backend.app.modules.game_systems.schemas.rules.rule_engines import RuleEngineVersionRead


_SYSTEMS = GameSystem.__table__
_DRAFTS = GameSystemRulesDraft.__table__
_VERSIONS = GameSystemRulesVersion.__table__

def _require_clean_session(session: AsyncSession) -> None:
	"""Не смешивать операцию с чужими ожидающими ORM-изменениями."""
	if session.new or session.dirty or session.deleted:
		raise RuntimeError(
			"Операция правил требует сессии "
			"без ожидающих ORM-изменений"
		)

def _rules_payload(value: RulesProfile | Mapping[str, Any]) -> dict[str, Any]:
	"""Получить независимый проверенный снимок числовых правил."""
	if isinstance(value, RulesProfile):
		raw = value.model_dump(mode="python")
	else:
		raw = dict(value)

	profile = RulesProfile.model_validate(raw)
	profile = validate_rules_profile(profile)

	return profile.model_dump(mode="json")

def _incoming_payload(profile: RulesProfile) -> dict[str, Any]:
	try:
		return _rules_payload(profile)
	except ValueError as exc:
		raise InvalidGameSystemRules(
			"Профиль или его начальное состояние недопустимы"
		) from exc

def _draft_read(row: Mapping[str, Any]) -> GameSystemRulesDraftRead:
	try:
		return GameSystemRulesDraftRead.model_validate(dict(row))
	except ValueError as exc:
		raise GameSystemRulesStorageError(
			"Сохранённый черновик имеет неподдерживаемый формат"
		) from exc

def _version_read(row: Mapping[str, Any]) -> GameSystemRulesVersionRead:
	try:
		return GameSystemRulesVersionRead.model_validate(dict(row))
	except ValueError as exc:
		raise GameSystemRulesStorageError(
			"Сохранённая публикация имеет неподдерживаемый формат"
		) from exc

def _check_revision(row: Mapping[str, Any], expected_revision: int) -> None:
	if row["revision"] != expected_revision:
		raise GameSystemRulesConflict(
			"Черновик уже изменён. Получите актуальную ревизию"
		)

def _check_draft_expectation(draft: Mapping[str, Any] | None, expected_revision: int | None) -> None:
	"""Проверить как наличие черновика, так и его ревизию."""
	if draft is None:
		if expected_revision is not None:
			raise GameSystemRulesConflict(
				"Черновик отсутствует. Получите актуальное состояние"
			)
		return

	if expected_revision is None:
		raise GameSystemRulesConflict(
			"Черновик уже существует. Получите актуальную ревизию"
		)

	_check_revision(draft, expected_revision)

def _require_standalone(row: Mapping[str, Any]) -> None:
	if (
			row["engine_version_id"] is not None
			or row["rules_overrides_json"] is not None
	):
		raise GameSystemRulesConflict(
			"Черновик связан с основой правил. "
			"Используйте выбор основы и переопределения"
		)

async def _get_system(session: AsyncSession, system_id: UUID, *, write: bool, active_only: bool) -> Mapping[str, Any]:
	result = await session.execute(
		select(_SYSTEMS)
		.where(_SYSTEMS.c.id == system_id)
		.with_for_update(read=not write)
	)
	system = result.mappings().one_or_none()

	if system is None:
		raise GameSystemNotFound("Игровая система не найдена")

	if active_only and not system["is_active"]:
		raise GameSystemNotFound("Игровая система не найдена")

	return system

async def _find_draft(session: AsyncSession, system_id: UUID, *, write: bool) -> Mapping[str, Any] | None:
	result = await session.execute(
		select(_DRAFTS)
		.where(_DRAFTS.c.system_id == system_id)
		.with_for_update(read=not write)
	)
	return result.mappings().one_or_none()

async def get_rules_draft(session: AsyncSession, system_id: UUID) -> GameSystemRulesDraftState:
	"""Чтение для редактора после проверки права управления."""
	_require_clean_session(session)

	await _get_system(
		session,
		system_id,
		write=False,
		active_only=False,
	)
	draft = await _find_draft(
		session,
		system_id,
		write=False,
	)

	return GameSystemRulesDraftState(
		draft=None if draft is None else _draft_read(draft),
	)

async def create_rules_draft(session: AsyncSession, system_id: UUID, data: GameSystemRulesDraftCreate) -> GameSystemRulesDraftRead:
	"""Создать самостоятельный черновик существующей системы."""
	data = GameSystemRulesDraftCreate.model_validate(
		data.model_dump(mode="python")
	)
	payload = _incoming_payload(data.rules)
	_require_clean_session(session)

	await _get_system(
		session,
		system_id,
		write=True,
		active_only=False,
	)
	existing = await _find_draft(
		session,
		system_id,
		write=True,
	)

	if existing is not None:
		raise GameSystemRulesConflict(
			"Черновик уже существует"
		)

	result = await session.execute(
		insert(_DRAFTS)
		.values(
			system_id=system_id,
			rules_json=payload,
			revision=1,
		)
		.returning(*_DRAFTS.c)
	)

	# Происхождение не передаётся:
	# nullable-столбцы без default получают SQL NULL.
	return _draft_read(result.mappings().one())

async def update_rules_draft(session: AsyncSession, system_id: UUID, data: GameSystemRulesDraftUpdate) -> GameSystemRulesDraftRead:
	"""Заменить правила только самостоятельного черновика."""
	data = GameSystemRulesDraftUpdate.model_validate(
		data.model_dump(mode="python")
	)
	payload = _incoming_payload(data.rules)
	_require_clean_session(session)

	await _get_system(
		session,
		system_id,
		write=True,
		active_only=False,
	)
	draft = await _find_draft(
		session,
		system_id,
		write=True,
	)

	if draft is None:
		raise GameSystemRulesConflict(
			"Черновик отсутствует"
		)

	_check_revision(draft, data.expected_revision)
	_require_standalone(draft)

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
		raise GameSystemRulesConflict(
			"Черновик изменился во время сохранения"
		)

	return _draft_read(saved)

async def set_rules_draft_engine(session: AsyncSession, system_id: UUID, actor_id: UUID, data: GameSystemDraftEngineSet) -> GameSystemRulesDraftRead:
	"""Явно выбрать основу и сохранить собранный черновик.

	Операция может:
	- создать связанный черновик;
	- перевести самостоятельный черновик на основу;
	- изменить основу или переопределения связанного черновика.

	Карточка системы и опубликованные версии не изменяются.
	"""
	data = GameSystemDraftEngineSet.model_validate(
		data.model_dump(mode="python")
	)
	_require_clean_session(session)

	system = await _get_system(
		session,
		system_id,
		write=True,
		active_only=False,
	)
	draft = await _find_draft(
		session,
		system_id,
		write=True,
	)
	_check_draft_expectation(
		draft,
		data.expected_revision,
	)

	source = EngineRulesSource(
		engine_id=data.engine_id,
		engine_version_id=data.engine_version_id,
		rules_overrides=data.rules_overrides,
	)

	assembled = await load_editor_engine_origin(
		session,
		source,
		actor_id,
		system["rules_engine_version"],
		draft,
	)

	if draft is None:
		result = await session.execute(
			insert(_DRAFTS)
			.values(
				system_id=system_id,
				revision=1,
				**assembled,
			)
			.returning(*_DRAFTS.c)
		)
		saved = result.mappings().one()
	else:
		result = await session.execute(
			update(_DRAFTS)
			.where(
				_DRAFTS.c.id == draft["id"],
				_DRAFTS.c.revision == data.expected_revision,
				)
			.values(
				**assembled,
				revision=_DRAFTS.c.revision + 1,
				updated_at=func.now(),
			)
			.returning(*_DRAFTS.c)
		)
		saved = result.mappings().one_or_none()

		if saved is None:
			raise GameSystemRulesConflict(
				"Черновик изменился во время выбора основы"
			)

	return _draft_read(saved)

async def publish_rules_version(session: AsyncSession, system_id: UUID, data: GameSystemRulesPublish) -> GameSystemRulesVersionRead:
	"""Опубликовать сохранённый профиль с проверкой происхождения.

	Публикация потребляет ревизию черновика.
	Новый профиль из тела запроса не принимается.
	"""
	data = GameSystemRulesPublish.model_validate(
		data.model_dump(mode="python")
	)
	_require_clean_session(session)

	system = await _get_system(
		session,
		system_id,
		write=True,
		active_only=False,
	)

	if not system["is_active"]:
		raise GameSystemRulesConflict(
			"Перед публикацией активируйте игровую систему"
		)

	draft = await _find_draft(
		session,
		system_id,
		write=True,
	)

	if draft is None:
		raise GameSystemRulesConflict(
			"Для публикации нужен сохранённый черновик"
		)

	_check_revision(draft, data.expected_revision)

	raw_rules = draft["rules_json"]

	if not isinstance(raw_rules, dict):
		raise GameSystemRulesConflict(
			"Исправьте формат черновика перед публикацией"
		)

	try:
		payload = _rules_payload(raw_rules)
	except ValueError as exc:
		raise GameSystemRulesConflict(
			"Сохранённый черновик не проходит проверку правил"
		) from exc

	# Для связанного профиля проверяет повторную сборку.
	# Для самостоятельного возвращает пустой словарь.
	origin = await origin_for_publication(
		session,
		draft,
		system["rules_engine_version"],
		payload,
	)

	number_result = await session.execute(
		select(
			func.coalesce(
				func.max(_VERSIONS.c.version_number),
				0,
			) + 1
		)
		.where(_VERSIONS.c.system_id == system_id)
	)
	next_number = number_result.scalar_one()

	version_result = await session.execute(
		insert(_VERSIONS)
		.values(
			system_id=system_id,
			version_number=next_number,
			rules_json=payload,
			rules_engine_version=system["rules_engine_version"],
			**origin,
		)
		.returning(*_VERSIONS.c)
	)
	response = _version_read(
		version_result.mappings().one()
	)

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
		raise GameSystemRulesConflict(
			"Черновик изменился во время публикации"
		)

	return response

async def get_latest_rules_version(session: AsyncSession, system_id: UUID, *, active_only: bool = True) -> GameSystemRulesVersionRead | None:
	"""Последняя публикация для каталога, не для расчёта листа."""
	_require_clean_session(session)

	await _get_system(
		session,
		system_id,
		write=False,
		active_only=active_only,
	)

	result = await session.execute(
		select(_VERSIONS)
		.where(_VERSIONS.c.system_id == system_id)
		.order_by(_VERSIONS.c.version_number.desc())
		.limit(1)
	)
	version = result.mappings().one_or_none()

	return None if version is None else _version_read(version)

async def get_rules_version(session: AsyncSession, system_id: UUID, version_id: UUID, *, active_only: bool = True) -> GameSystemRulesVersionRead:
	"""Прочитать конкретную публикацию указанной системы."""
	_require_clean_session(session)

	await _get_system(
		session,
		system_id,
		write=False,
		active_only=active_only,
	)

	result = await session.execute(
		select(_VERSIONS)
		.where(
			_VERSIONS.c.id == version_id,
			_VERSIONS.c.system_id == system_id,
			)
	)
	version = result.mappings().one_or_none()

	if version is None:
		raise GameSystemNotFound(
			"Публикация игровой системы не найдена"
		)

	return _version_read(version)

def _editor_read(system: Mapping[str, Any], draft: Mapping[str, Any]) -> GameSystemEditorRead:
	"""Проверить полный ответ до фиксации изменений."""
	try:
		return GameSystemEditorRead(
			system=GameSystemAdminRead.model_validate(dict(system)),
			draft=_draft_read(draft),
		)
	except ValueError as exc:
		raise GameSystemRulesStorageError("Карточка или черновик имеют неподдерживаемый формат") from exc

def _engine_source(data: GameSystemFromEngineCreate | GameSystemEngineEditorUpdate) -> EngineRulesSource:
	"""Передать загрузчику только поля выбора основы."""
	return EngineRulesSource(
		engine_id=data.engine_id,
		engine_version_id=data.engine_version_id,
		rules_overrides=data.rules_overrides,
	)

async def _check_card_unique(session: AsyncSession, data: GameSystemCreate, exclude_id: UUID | None = None) -> None:
	query = select(_SYSTEMS.c.id).where(or_(_SYSTEMS.c.name == data.name, _SYSTEMS.c.slug == data.slug))

	if exclude_id is not None:
		query = query.where(_SYSTEMS.c.id != exclude_id)

	result = await session.execute(query.limit(1))

	if result.scalar_one_or_none() is not None:
		raise GameSystemRulesConflict("Игровая система с таким названием или кодом уже существует")

async def _insert_editor_draft(session: AsyncSession, system_id: UUID, values: dict[str, Any]) -> Mapping[str, Any]:
	result = await session.execute(
		insert(_DRAFTS)
		.values(system_id=system_id, revision=1, **values)
		.returning(*_DRAFTS.c)
	)
	return result.mappings().one()

async def _create_editor_state(session: AsyncSession, data: GameSystemCreate, values: dict[str, Any]) -> GameSystemEditorRead:
	await _check_card_unique(session, data)

	result = await session.execute(
		insert(_SYSTEMS)
		.values(**data.model_dump())
		.returning(*_SYSTEMS.c)
	)
	system = result.mappings().one()
	draft = await _insert_editor_draft(session, system["id"], values)
	return _editor_read(system, draft)

async def _lock_editor_state(session: AsyncSession, system_id: UUID, data: GameSystemEditorUpdate | GameSystemEngineEditorUpdate
                             ) -> tuple[Mapping[str, Any], Mapping[str, Any] | None]:
	system = await _get_system(session, system_id, write=True, active_only=False)
	draft = await _find_draft(session, system_id, write=True)
	_check_draft_expectation(draft, data.expected_revision)

	if data.system.rules_engine_version != system["rules_engine_version"]:
		raise GameSystemRulesConflict("Изменение версии программного исполнителя не поддерживается этой формой")

	return system, draft

async def _save_editor_state(session: AsyncSession, system_id: UUID, data: GameSystemEditorUpdate | GameSystemEngineEditorUpdate,
                             draft: Mapping[str, Any] | None, values: dict[str, Any]) -> GameSystemEditorRead:
	await _check_card_unique(session, data.system, exclude_id=system_id)

	result = await session.execute(
		update(_SYSTEMS)
		.where(_SYSTEMS.c.id == system_id)
		.values(**data.system.model_dump(), updated_at=func.now())
		.returning(*_SYSTEMS.c)
	)
	system = result.mappings().one_or_none()

	if system is None:
		raise GameSystemRulesConflict("Карточка изменилась во время сохранения")

	if draft is None:
		saved_draft = await _insert_editor_draft(session, system_id, values)
	else:
		result = await session.execute(
			update(_DRAFTS)
			.where(_DRAFTS.c.id == draft["id"], _DRAFTS.c.revision == data.expected_revision)
			.values(**values, revision=_DRAFTS.c.revision + 1, updated_at=func.now())
			.returning(*_DRAFTS.c)
		)
		saved_draft = result.mappings().one_or_none()

		if saved_draft is None:
			raise GameSystemRulesConflict("Черновик изменился во время сохранения. Изменения карточки и правил отменены")

	return _editor_read(system, saved_draft)

async def create_system_with_draft(session: AsyncSession, data: GameSystemEditorCreate) -> GameSystemEditorRead:
	"""Подготовить карточку и самостоятельный черновик в одной транзакции."""
	_require_clean_session(session)
	data = GameSystemEditorCreate.model_validate(data.model_dump(mode="python"))
	payload = _incoming_payload(data.rules)
	return await _create_editor_state(session, data.system, {"rules_json": payload})

async def update_system_with_draft(session: AsyncSession, system_id: UUID, data: GameSystemEditorUpdate) -> GameSystemEditorRead:
	"""Обновить карточку и самостоятельный черновик с проверкой ревизии."""
	_require_clean_session(session)
	data = GameSystemEditorUpdate.model_validate(data.model_dump(mode="python"))
	payload = _incoming_payload(data.rules)
	_, draft = await _lock_editor_state(session, system_id, data)

	if draft is not None:
		_require_standalone(draft)

	return await _save_editor_state(session, system_id, data, draft, {"rules_json": payload})

async def create_system_from_engine(session: AsyncSession, actor_id: UUID, data: GameSystemFromEngineCreate) -> GameSystemEditorRead:
	"""Создать карточку и черновик на доступной опубликованной основе."""
	_require_clean_session(session)
	data = GameSystemFromEngineCreate.model_validate(data.model_dump(mode="python"))
	source = _engine_source(data)
	values = await load_engine_origin(session, source, actor_id, data.system.rules_engine_version)
	return await _create_editor_state(session, data.system, values)

async def update_system_from_engine(session: AsyncSession, system_id: UUID, actor_id: UUID, data: GameSystemEngineEditorUpdate) -> GameSystemEditorRead:
	"""Сохранить карточку, основу и переопределения в одной транзакции."""
	_require_clean_session(session)
	data = GameSystemEngineEditorUpdate.model_validate(data.model_dump(mode="python"))
	system, draft = await _lock_editor_state(session, system_id, data)
	source = _engine_source(data)
	values = await load_editor_engine_origin(session, source, actor_id, system["rules_engine_version"], draft)
	return await _save_editor_state(session, system_id, data, draft, values)

async def get_system_engine_origin(session: AsyncSession, system_id: UUID) -> GameSystemEngineOriginRead:
	"""Прочитать основу уже сохранённого черновика после проверки прав."""
	_require_clean_session(session)
	await _get_system(session, system_id, write=False, active_only=False)
	draft = await _find_draft(session, system_id, write=False)

	if draft is None:
		raise GameSystemNotFound("Черновик игровой системы не найден")

	version = await load_saved_engine_version(session, draft)

	try:
		return GameSystemEngineOriginRead(
			draft_revision=draft["revision"],
			engine_version=RuleEngineVersionRead.model_validate(dict(version)),
		)
	except ValueError as exc:
		raise GameSystemRulesStorageError("Сохранённая основа имеет неподдерживаемый формат") from exc