# backend/app/modules/game_systems/services/editor_service.py

"""Черновики и публикации правил существующих игровых систем.

Правила системы хранятся раздельно: числовая механика и текстовые главы
живут в собственных черновиках и версиях, а опубликованный выпуск
описывается комплектом (``game_system_versions``).

Для редактора оба блока остаются одним документом ``RulesProfile``:
форма получает собранный профиль и отдаёт его целиком. Поэтому ревизии
черновика механики и черновика текста пишутся синхронно и всегда равны;
ожидаемая ревизия проверяется по механике и подтверждается текстом.

Происхождение от основы правил относится только к механике: текстовые
главы автономны и основой не перезаписываются.

Административные права проверяет вызывающий слой.
Сервис не выполняет commit или rollback.

Порядок блокировок при изменении:
система -> черновик механики -> черновик текста -> карточка новой основы.

Опубликованные строки этим сервисом не изменяются.
"""

from __future__ import annotations
from collections.abc import Mapping
from typing import Any
from uuid import UUID
from sqlalchemy import func, insert, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.modules.game_systems.errors import (GameSystemNotFound, GameSystemRulesConflict, GameSystemRulesStorageError, InvalidGameSystemRules)
from backend.app.modules.game_systems.models.game_systems import (GameSystem)
from backend.app.modules.game_systems.models.system_versions import (GameSystemMechanicDraft, GameSystemMechanicVersion, GameSystemTextDraft, GameSystemTextVersion, GameSystemVersion)
from backend.app.modules.game_systems.rules.mechanic_codec import (mechanic_to_profile, profile_to_mechanic, profile_to_text, split_overrides)
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
from backend.app.modules.game_systems.schemas.game_rules import GameSystemRulesVersionPage, GameSystemRulesVersionSummary


_SYSTEMS = GameSystem.__table__
_MECHANIC_DRAFTS = GameSystemMechanicDraft.__table__
_TEXT_DRAFTS = GameSystemTextDraft.__table__
_MECHANIC_VERSIONS = GameSystemMechanicVersion.__table__
_TEXT_VERSIONS = GameSystemTextVersion.__table__
_SYSTEM_VERSIONS = GameSystemVersion.__table__

def _require_clean_session(session: AsyncSession) -> None:
	"""Не смешивать операцию с чужими ожидающими ORM-изменениями."""
	if session.new or session.dirty or session.deleted:
		raise RuntimeError(
			"Операция правил требует сессии "
			"без ожидающих ORM-изменений"
		)

def _rules_payload(value: RulesProfile | Mapping[str, Any]) -> dict[str, Any]:
	"""Получить независимый проверенный снимок правил."""
	if isinstance(value, RulesProfile):
		raw = value.model_dump(mode="python")
	else:
		raw = dict(value)

	profile = RulesProfile.model_validate(raw)
	profile = validate_rules_profile(profile)

	return profile.model_dump(mode="json")

def _incoming_payload(profile: RulesProfile | None) -> dict[str, Any]:
	"""Проверить сохраняемый черновик без выполнения начальных расчётов.

	Если профиль не передан — возвращается пустой валидный черновик,
	чтобы система в разработке могла существовать без правил.
	"""
	if profile is None:
		empty = RulesProfile.model_validate({
			"schema_version": 4,
			"calculations": {"attributes": {}, "derived": {}},
			"initial_attributes": {},
			"resources": {},
		})
		return empty.model_dump(mode="json")

	try:
		checked = RulesProfile.model_validate(profile.model_dump(mode="python"))
		return checked.model_dump(mode="json")
	except ValueError as exc:
		raise InvalidGameSystemRules(
			"Структура профиля или его начальные значения недопустимы"
		) from exc

def _chapters_of(text: Mapping[str, Any] | None) -> dict[str, Any]:
	"""Извлечь главы черновика текста; отсутствующий черновик — пустой текст."""
	if text is None:
		return {}

	text_json = text["text_json"]

	if not isinstance(text_json, dict):
		raise GameSystemRulesStorageError(
			"Сохранённый черновик текста имеет неподдерживаемый формат"
		)

	received = text_json.get("chapters")

	return dict(received) if isinstance(received, dict) else {}

def _draft_view(mechanic: Mapping[str, Any], text: Mapping[str, Any] | None) -> dict[str, Any]:
	"""Собрать единое представление черновика из механики и текста.

	Форма редактора работает с одним профилем правил, поэтому от пары
	остаётся тот же набор полей, что и у прежнего единого черновика.
	Идентификатор и ревизия берутся из механики: она обязательна.
	"""
	mechanic_json = mechanic["mechanic_json"]

	if not isinstance(mechanic_json, dict):
		raise GameSystemRulesStorageError(
			"Сохранённый черновик механики имеет неподдерживаемый формат"
		)

	try:
		rules = {**mechanic_to_profile(mechanic_json), "rulebook": _chapters_of(text)}
	except ValueError as exc:
		raise GameSystemRulesStorageError(
			"Сохранённый черновик не собирается в профиль правил"
		) from exc

	return {
		"id": mechanic["id"],
		"system_id": mechanic["system_id"],
		"revision": mechanic["revision"],
		"engine_version_id": mechanic["engine_version_id"],
		"rules_overrides_json": mechanic["mechanic_overrides_json"],
		"rules_json": rules,
		"created_at": mechanic["created_at"],
		"updated_at": mechanic["updated_at"],
	}

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

def _split_values(payload: Mapping[str, Any], *, engine_version_id: Any = None,
	rules_overrides: Mapping[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
	"""Разрезать профиль на значения черновиков механики и текста.

	Происхождение оформляется только парой (основа, переопределения) и
	только числовыми разделами: текстовые главы в переопределениях не
	хранятся.
	"""
	mechanic_values: dict[str, Any] = {
		"mechanic_json": profile_to_mechanic(payload),
	}

	if engine_version_id is not None:
		mechanic_values["engine_version_id"] = engine_version_id
		mechanic_values["mechanic_overrides_json"] = split_overrides(dict(rules_overrides or {}))

	text_values: dict[str, Any] = {
		"text_json": profile_to_text(payload),
	}

	return mechanic_values, text_values

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

async def _find_draft_rows(session: AsyncSession, system_id: UUID,
	*, write: bool) -> tuple[Mapping[str, Any] | None, Mapping[str, Any] | None]:
	"""Заблокировать и прочитать пару черновиков в согласованном порядке."""
	mechanic_result = await session.execute(
		select(_MECHANIC_DRAFTS)
		.where(_MECHANIC_DRAFTS.c.system_id == system_id)
		.with_for_update(read=not write)
	)
	mechanic = mechanic_result.mappings().one_or_none()

	text_result = await session.execute(
		select(_TEXT_DRAFTS)
		.where(_TEXT_DRAFTS.c.system_id == system_id)
		.with_for_update(read=not write)
	)

	return mechanic, text_result.mappings().one_or_none()

async def _find_draft(session: AsyncSession, system_id: UUID,
	*, write: bool) -> dict[str, Any] | None:
	"""Прочитать черновик системы как единый документ или None."""
	mechanic, text = await _find_draft_rows(session, system_id, write=write)

	if mechanic is None:
		return None

	return _draft_view(mechanic, text)

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

async def _insert_draft_pair(session: AsyncSession, system_id: UUID, revision: int,
	mechanic_values: dict[str, Any], text_values: dict[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
	"""Создать оба черновика с одной ревизией."""
	mechanic_result = await session.execute(
		insert(_MECHANIC_DRAFTS)
		.values(system_id=system_id, revision=revision, **mechanic_values)
		.returning(*_MECHANIC_DRAFTS.c)
	)
	mechanic = mechanic_result.mappings().one()

	text_result = await session.execute(
		insert(_TEXT_DRAFTS)
		.values(system_id=system_id, revision=revision, **text_values)
		.returning(*_TEXT_DRAFTS.c)
	)

	return mechanic, text_result.mappings().one()

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
	mechanic, _ = await _find_draft_rows(
		session,
		system_id,
		write=True,
	)

	if mechanic is not None:
		raise GameSystemRulesConflict(
			"Черновик уже существует"
		)

	# Происхождение не передаётся:
	# nullable-столбцы без default получают SQL NULL.
	mechanic_values, text_values = _split_values(payload)
	saved_mechanic, saved_text = await _insert_draft_pair(
		session, system_id, 1, mechanic_values, text_values
	)

	return _draft_read(_draft_view(saved_mechanic, saved_text))

async def _update_draft_pair(session: AsyncSession, mechanic: Mapping[str, Any],
	text: Mapping[str, Any] | None, expected_revision: int,
	mechanic_values: dict[str, Any], text_values: dict[str, Any], problem: str,
	) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
	"""Заменить оба черновика при совпадении ожидаемой ревизии.

	Ревизии пишутся синхронно, поэтому условием обновления текста служит
	та же ожидаемая ревизия. Отсутствие строки текста означает черновик,
	созданный до разделения блоков: он заводится текущим содержимым.
	"""
	mechanic_result = await session.execute(
		update(_MECHANIC_DRAFTS)
		.where(
			_MECHANIC_DRAFTS.c.id == mechanic["id"],
			_MECHANIC_DRAFTS.c.revision == expected_revision,
			)
		.values(
			**mechanic_values,
			revision=_MECHANIC_DRAFTS.c.revision + 1,
			updated_at=func.now(),
		)
		.returning(*_MECHANIC_DRAFTS.c)
	)
	saved_mechanic = mechanic_result.mappings().one_or_none()

	if saved_mechanic is None:
		raise GameSystemRulesConflict(problem)

	next_revision = saved_mechanic["revision"]

	if text is None:
		text_result = await session.execute(
			insert(_TEXT_DRAFTS)
			.values(system_id=mechanic["system_id"], revision=next_revision, **text_values)
			.returning(*_TEXT_DRAFTS.c)
		)

		return saved_mechanic, text_result.mappings().one()

	text_result = await session.execute(
		update(_TEXT_DRAFTS)
		.where(
			_TEXT_DRAFTS.c.id == text["id"],
			_TEXT_DRAFTS.c.revision == expected_revision,
			)
		.values(
			**text_values,
			revision=next_revision,
			updated_at=func.now(),
		)
		.returning(*_TEXT_DRAFTS.c)
	)
	saved_text = text_result.mappings().one_or_none()

	if saved_text is None:
		raise GameSystemRulesConflict(problem)

	return saved_mechanic, saved_text

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
	mechanic, text = await _find_draft_rows(
		session,
		system_id,
		write=True,
	)

	if mechanic is None:
		raise GameSystemRulesConflict(
			"Черновик отсутствует"
		)

	draft = _draft_view(mechanic, text)
	_check_revision(draft, data.expected_revision)
	_require_standalone(draft)

	mechanic_values, text_values = _split_values(payload)
	saved_mechanic, saved_text = await _update_draft_pair(
		session,
		mechanic,
		text,
		data.expected_revision,
		mechanic_values,
		text_values,
		"Черновик изменился во время сохранения",
	)

	return _draft_read(_draft_view(saved_mechanic, saved_text))

async def set_rules_draft_engine(session: AsyncSession, system_id: UUID, actor_id: UUID, data: GameSystemDraftEngineSet) -> GameSystemRulesDraftRead:
	"""Явно выбрать основу и сохранить собранный черновик.

	Операция может:
	- создать связанный черновик;
	- перевести самостоятельный черновик на основу;
	- изменить основу или переопределения связанного черновика.

	Механика собирается из основы и переопределений. Текстовые главы
	остаются собственными главами черновика: основа их не заменяет.

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
	mechanic, text = await _find_draft_rows(
		session,
		system_id,
		write=True,
	)
	draft = None if mechanic is None else _draft_view(mechanic, text)
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
	mechanic_values, text_values = _split_values(
		assembled["rules_json"],
		engine_version_id=assembled["engine_version_id"],
		rules_overrides=assembled["rules_overrides_json"],
	)

	# Главы черновика автономны: собранный из основы текст не перезаписывает
	# уже сохранённые главы.
	if draft is not None:
		text_values["text_json"] = {"schema_version": 1, "chapters": _chapters_of(text)}

	if mechanic is None:
		saved_mechanic, saved_text = await _insert_draft_pair(
			session, system_id, 1, mechanic_values, text_values
		)
	else:
		saved_mechanic, saved_text = await _update_draft_pair(
			session,
			mechanic,
			text,
			data.expected_revision,
			mechanic_values,
			text_values,
			"Черновик изменился во время выбора основы",
		)

	return _draft_read(_draft_view(saved_mechanic, saved_text))

async def _next_number(session: AsyncSession, source, system_id: UUID) -> int:
	result = await session.execute(
		select(func.coalesce(func.max(source.c.version_number), 0) + 1)
		.where(source.c.system_id == system_id)
	)

	return result.scalar_one()

async def publish_rules_version(session: AsyncSession, system_id: UUID, data: GameSystemRulesPublish) -> GameSystemRulesVersionRead:
	"""Опубликовать сохранённый профиль с проверкой происхождения.

	Публикация потребляет ревизию черновика.
	Новый профиль из тела запроса не принимается.

	Создаются версия механики, версия текста (при непустых главах) и
	комплект, который связывает их и закрепляется за системой как текущая
	версия. Идентификатор комплекта и отдаётся вызывающему слою: именно он
	ссылка для листов и игр.
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

	mechanic, text = await _find_draft_rows(
		session,
		system_id,
		write=True,
	)

	if mechanic is None:
		raise GameSystemRulesConflict(
			"Для публикации нужен сохранённый черновик"
		)

	draft = _draft_view(mechanic, text)
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

	chapters = payload.get("rulebook") or {}

	# Происхождение проверяется по числовой части: текстовые главы в него
	# не входят, иначе сохранённый текст ложно считался бы расхождением.
	mechanic_payload = profile_to_mechanic(payload)
	origin = await origin_for_publication(
		session,
		draft,
		system["rules_engine_version"],
		mechanic_payload,
	)
	engine_version_id = origin.get("engine_version_id")
	rules_overrides = origin.get("rules_overrides_json")

	# JSONB сериализует Python None в JSON null, а не в SQL NULL. Для
	# самостоятельного черновика поля происхождения должны остаться
	# отсутствующими: ограничение БД различает SQL NULL и jsonb 'null'.
	mechanic_version_values: dict[str, Any] = {
		"system_id": system_id,
		"version_number": await _next_number(session, _MECHANIC_VERSIONS, system_id),
		"source_draft_revision": data.expected_revision,
		"mechanic_json": mechanic_payload,
		"rules_engine_version": system["rules_engine_version"],
	}

	if engine_version_id is not None:
		mechanic_version_values["engine_version_id"] = engine_version_id
		mechanic_version_values["mechanic_overrides_json"] = rules_overrides

	mechanic_version = (await session.execute(
		insert(_MECHANIC_VERSIONS)
		.values(**mechanic_version_values)
		.returning(*_MECHANIC_VERSIONS.c)
	)).mappings().one()

	text_version_id = None

	if chapters:
		text_version = (await session.execute(
			insert(_TEXT_VERSIONS)
			.values(
				system_id=system_id,
				version_number=await _next_number(session, _TEXT_VERSIONS, system_id),
				source_draft_revision=data.expected_revision,
				text_json={"schema_version": 1, "chapters": chapters},
			)
			.returning(*_TEXT_VERSIONS.c)
		)).mappings().one()

		text_version_id = text_version["id"]

	bundle = (await session.execute(
		insert(_SYSTEM_VERSIONS)
		.values(
			system_id=system_id,
			version_number=await _next_number(session, _SYSTEM_VERSIONS, system_id),
			text_version_id=text_version_id,
			mechanic_version_id=mechanic_version["id"],
		)
		.returning(*_SYSTEM_VERSIONS.c)
	)).mappings().one()

	# Комплект становится текущим: читатели (листы, игры, обзор) читают
	# именно game_systems.current_version_id.
	await session.execute(
		update(_SYSTEMS)
		.where(_SYSTEMS.c.id == system_id)
		.values(current_version_id=bundle["id"])
	)

	# Ревизия потребляется обоими черновиками: публикация относится к паре.
	consumed = (await session.execute(
		update(_MECHANIC_DRAFTS)
		.where(
			_MECHANIC_DRAFTS.c.id == mechanic["id"],
			_MECHANIC_DRAFTS.c.revision == data.expected_revision,
			)
		.values(
			is_published=True,
			revision=_MECHANIC_DRAFTS.c.revision + 1,
			updated_at=func.now(),
		)
		.returning(_MECHANIC_DRAFTS.c.revision)
	)).scalar_one_or_none()

	if consumed is None:
		raise GameSystemRulesConflict(
			"Черновик изменился во время публикации"
		)

	if text is not None:
		await session.execute(
			update(_TEXT_DRAFTS)
			.where(
				_TEXT_DRAFTS.c.id == text["id"],
				_TEXT_DRAFTS.c.revision == data.expected_revision,
				)
			.values(
				is_published=True,
				revision=_TEXT_DRAFTS.c.revision + 1,
				updated_at=func.now(),
			)
		)

	return _version_read({
		"id": bundle["id"],
		"system_id": system_id,
		"version_number": bundle["version_number"],
		"engine_version_id": engine_version_id,
		"rules_overrides_json": rules_overrides,
		"rules_json": payload,
		"rules_engine_version": mechanic_version["rules_engine_version"],
		"published_at": bundle["published_at"],
	})

async def _load_version(session: AsyncSession, system_id: UUID, bundle: Mapping[str, Any]) -> dict[str, Any]:
	"""Собрать публикацию из комплекта, его механики и его текста."""
	mechanic = (await session.execute(
		select(_MECHANIC_VERSIONS).where(_MECHANIC_VERSIONS.c.id == bundle["mechanic_version_id"])
	)).mappings().one_or_none()

	if mechanic is None:
		raise GameSystemRulesStorageError(
			"Версия механики комплекта не найдена"
		)

	text = None

	if bundle["text_version_id"] is not None:
		text = (await session.execute(
			select(_TEXT_VERSIONS).where(_TEXT_VERSIONS.c.id == bundle["text_version_id"])
		)).mappings().one_or_none()

		if text is None:
			raise GameSystemRulesStorageError(
				"Версия текстовых правил комплекта не найдена"
			)

	mechanic_json = mechanic["mechanic_json"]

	if not isinstance(mechanic_json, dict):
		raise GameSystemRulesStorageError(
			"Версия механики имеет неподдерживаемый формат"
		)

	try:
		rules = {**mechanic_to_profile(mechanic_json), "rulebook": _chapters_of(text)}
	except ValueError as exc:
		raise GameSystemRulesStorageError(
			"Сохранённый комплект не собирается в профиль правил"
		) from exc

	return {
		"id": bundle["id"],
		"system_id": system_id,
		"version_number": bundle["version_number"],
		"engine_version_id": mechanic["engine_version_id"],
		"rules_overrides_json": mechanic["mechanic_overrides_json"],
		"rules_json": rules,
		"rules_engine_version": mechanic["rules_engine_version"],
		"published_at": bundle["published_at"],
	}

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
		select(_SYSTEM_VERSIONS)
		.where(_SYSTEM_VERSIONS.c.system_id == system_id)
		.order_by(_SYSTEM_VERSIONS.c.version_number.desc())
		.limit(1)
	)
	bundle = result.mappings().one_or_none()

	return None if bundle is None else _version_read(await _load_version(session, system_id, bundle))

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
		select(_SYSTEM_VERSIONS)
		.where(
			_SYSTEM_VERSIONS.c.id == version_id,
			_SYSTEM_VERSIONS.c.system_id == system_id,
			)
	)
	bundle = result.mappings().one_or_none()

	if bundle is None:
		raise GameSystemNotFound(
			"Публикация игровой системы не найдена"
		)

	return _version_read(await _load_version(session, system_id, bundle))

async def list_publications(session: AsyncSession, system_id: UUID, *, active_only: bool = True, limit: int = 20, before: int | None = None):
	"""Прочитать метаданные публикаций, не загружая профили правил."""
	_require_clean_session(session)

	if type(limit) is not int or not 1 <= limit <= 100:
		raise InvalidGameSystemRules("Размер страницы должен быть целым числом от 1 до 100")

	if before is not None and (type(before) is not int or before < 1):
		raise InvalidGameSystemRules("Граница истории должна быть положительным целым числом")

	await _get_system(session, system_id, write=False, active_only=active_only)

	# Номер исполнителя принадлежит механике: комплект наследует её основу.
	query = (
		select(
			_SYSTEM_VERSIONS.c.id,
			_SYSTEM_VERSIONS.c.system_id,
			_SYSTEM_VERSIONS.c.version_number,
			_MECHANIC_VERSIONS.c.rules_engine_version,
			_SYSTEM_VERSIONS.c.published_at,
		)
		.select_from(
			_SYSTEM_VERSIONS.join(
				_MECHANIC_VERSIONS,
				_MECHANIC_VERSIONS.c.id == _SYSTEM_VERSIONS.c.mechanic_version_id,
				)
		)
		.where(_SYSTEM_VERSIONS.c.system_id == system_id)
	)

	if before is not None:
		query = query.where(_SYSTEM_VERSIONS.c.version_number < before)

	result = await session.execute(
		query.order_by(_SYSTEM_VERSIONS.c.version_number.desc()).limit(limit + 1)
	)

	rows = list(result.mappings().all())

	try:
		items = [
			GameSystemRulesVersionSummary.model_validate(dict(row))
			for row in rows[:limit]
		]

		next_before = items[-1].version_number if len(rows) > limit else None

		return GameSystemRulesVersionPage(items=items, next_before=next_before)
	except ValueError as exc:
		raise GameSystemRulesStorageError("Не удалось прочитать метаданные публикаций") from exc

async def set_current_rules_version(session: AsyncSession, system_id: UUID, version_id: UUID) -> GameSystemRulesVersionRead | None:
	"""Установить публикацию как активную для системы.

	Версия системы — это комплект, поэтому закрепляется его идентификатор.
	Возвращает установленную версию или None, если версия не найдена.
	"""
	_require_clean_session(session)

	system = await _get_system(
		session,
		system_id,
		write=True,
		active_only=False,
	)

	result = await session.execute(
		select(_SYSTEM_VERSIONS)
		.where(
			_SYSTEM_VERSIONS.c.id == version_id,
			_SYSTEM_VERSIONS.c.system_id == system_id,
			)
	)
	bundle = result.mappings().one_or_none()

	if bundle is None:
		raise GameSystemNotFound(
			"Публикация не найдена или не принадлежит этой системе"
		)

	await session.execute(
		update(_SYSTEMS)
		.where(_SYSTEMS.c.id == system_id)
		.values(current_version_id=version_id)
	)

	return _version_read(await _load_version(session, system_id, bundle))

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

async def _create_editor_state(session: AsyncSession, data: GameSystemCreate, payload: Mapping[str, Any],
	*, engine_version_id: Any = None, rules_overrides: Mapping[str, Any] | None = None) -> GameSystemEditorRead:
	await _check_card_unique(session, data)

	result = await session.execute(
		insert(_SYSTEMS)
		.values(**data.model_dump())
		.returning(*_SYSTEMS.c)
	)
	system = result.mappings().one()
	mechanic_values, text_values = _split_values(
		payload, engine_version_id=engine_version_id, rules_overrides=rules_overrides
	)
	mechanic, text = await _insert_draft_pair(session, system["id"], 1, mechanic_values, text_values)

	return _editor_read(system, _draft_view(mechanic, text))

async def _lock_editor_state(session: AsyncSession, system_id: UUID,
	data: GameSystemEditorUpdate | GameSystemEngineEditorUpdate) -> tuple[Mapping[str, Any], Mapping[str, Any] | None, Mapping[str, Any] | None, dict[str, Any] | None]:
	system = await _get_system(session, system_id, write=True, active_only=False)
	mechanic, text = await _find_draft_rows(session, system_id, write=True)
	draft = None if mechanic is None else _draft_view(mechanic, text)
	_check_draft_expectation(draft, data.expected_revision)

	if data.system.rules_engine_version != system["rules_engine_version"]:
		raise GameSystemRulesConflict("Изменение версии программного исполнителя не поддерживается этой формой")

	return system, mechanic, text, draft

async def _save_editor_state(session: AsyncSession, system_id: UUID, data: GameSystemEditorUpdate | GameSystemEngineEditorUpdate,
	mechanic: Mapping[str, Any] | None, text: Mapping[str, Any] | None,
	mechanic_values: dict[str, Any], text_values: dict[str, Any]) -> GameSystemEditorRead:
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

	if mechanic is None:
		saved_mechanic, saved_text = await _insert_draft_pair(
			session, system_id, 1, mechanic_values, text_values
		)
	else:
		saved_mechanic, saved_text = await _update_draft_pair(
			session,
			mechanic,
			text,
			data.expected_revision,
			mechanic_values,
			text_values,
			"Черновик изменился во время сохранения. Изменения карточки и правил отменены",
		)

	return _editor_read(system, _draft_view(saved_mechanic, saved_text))

async def create_system_with_draft(session: AsyncSession, data: GameSystemEditorCreate) -> GameSystemEditorRead:
	"""Подготовить карточку и самостоятельный черновик в одной транзакции."""
	_require_clean_session(session)
	data = GameSystemEditorCreate.model_validate(data.model_dump(mode="python"))

	return await _create_editor_state(session, data.system, _incoming_payload(data.rules))

async def update_system_with_draft(session: AsyncSession, system_id: UUID, data: GameSystemEditorUpdate) -> GameSystemEditorRead:
	"""Обновить карточку и самостоятельный черновик с проверкой ревизии."""
	_require_clean_session(session)
	data = GameSystemEditorUpdate.model_validate(data.model_dump(mode="python"))
	payload = _incoming_payload(data.rules)
	_, mechanic, text, draft = await _lock_editor_state(session, system_id, data)

	if draft is not None:
		_require_standalone(draft)

	mechanic_values, text_values = _split_values(payload)

	return await _save_editor_state(session, system_id, data, mechanic, text, mechanic_values, text_values)

async def create_system_from_engine(session: AsyncSession, actor_id: UUID, data: GameSystemFromEngineCreate) -> GameSystemEditorRead:
	"""Создать карточку и черновик на доступной опубликованной основе."""
	_require_clean_session(session)
	data = GameSystemFromEngineCreate.model_validate(data.model_dump(mode="python"))
	source = _engine_source(data)
	assembled = await load_engine_origin(session, source, actor_id, data.system.rules_engine_version)

	return await _create_editor_state(
		session,
		data.system,
		assembled["rules_json"],
		engine_version_id=assembled["engine_version_id"],
		rules_overrides=assembled["rules_overrides_json"],
	)

async def update_system_from_engine(session: AsyncSession, system_id: UUID, actor_id: UUID, data: GameSystemEngineEditorUpdate) -> GameSystemEditorRead:
	"""Сохранить карточку, основу и переопределения в одной транзакции.

	Механика пересобирается из основы и переопределений. Сохранённые главы
	текста остаются без изменений: текстовые правила не зависят от основы.
	"""
	_require_clean_session(session)
	data = GameSystemEngineEditorUpdate.model_validate(data.model_dump(mode="python"))
	system, mechanic, text, draft = await _lock_editor_state(session, system_id, data)
	source = _engine_source(data)
	assembled = await load_editor_engine_origin(session, source, actor_id, system["rules_engine_version"], draft)
	mechanic_values, text_values = _split_values(
		assembled["rules_json"],
		engine_version_id=assembled["engine_version_id"],
		rules_overrides=assembled["rules_overrides_json"],
	)

	if draft is not None:
		text_values["text_json"] = {"schema_version": 1, "chapters": _chapters_of(text)}

	return await _save_editor_state(session, system_id, data, mechanic, text, mechanic_values, text_values)

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


async def lock_rules_draft_for_migration(session: AsyncSession, system_id: UUID) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
	"""Заблокировать карточку и черновик перед переносом раздела rulebook.

	Перенос создаёт книгу и не изменяет черновик системы, поэтому
	блокировка на запись нужна для сериализации с одновременным
	редактированием правил: без неё книга могла бы перенести тексты,
	которые черновик уже отбросил.

	Возвращает заблокированные карточку и черновик в едином представлении.
	"""
	_require_clean_session(session)

	system = await _get_system(session, system_id, write=True, active_only=False)
	draft = await _find_draft(session, system_id, write=True)

	if draft is None:
		raise GameSystemRulesConflict("Для переноса нужен сохранённый черновик правил")

	if not isinstance(draft["rules_json"], dict):
		raise GameSystemRulesConflict("Исправьте формат черновика перед переносом")

	return system, draft
