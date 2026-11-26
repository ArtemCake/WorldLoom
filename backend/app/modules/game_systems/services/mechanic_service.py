# backend/app/modules/game_systems/services/mechanic_service.py

"""Черновики и публикации механики (числовой профиль системы).

Сервис оперирует таблицей `game_system_mechanic_drafts` и
`game_system_mechanic_versions`. Все операции используют
`mechanic_json` как исполняемый профиль.

Публикация механики требует привязки к версии движка правил:
`rules_engine_version` берётся из карточки системы.
"""

from __future__ import annotations
from typing import Any
from uuid import UUID
from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.modules.game_systems.errors import (
    GameSystemNotFound,
    GameSystemRulesConflict,
    GameSystemRulesStorageError,
    InvalidGameSystemRules,
)
from backend.app.modules.game_systems.models.game_systems import GameSystem
from backend.app.modules.game_systems.models.system_versions import (
    GameSystemMechanicDraft,
    GameSystemMechanicVersion,
)
from backend.app.modules.game_systems.rules.rules_engine import (
    validate_rules_profile,
)
from backend.app.modules.game_systems.schemas.game_system_versions import (
    SystemMechanicContent,
    GameSystemMechanicDraftCreate,
    GameSystemMechanicDraftRead,
    GameSystemMechanicDraftState,
    GameSystemMechanicDraftUpdate,
    GameSystemMechanicPublish,
    GameSystemMechanicVersionPage,
    GameSystemMechanicVersionRead,
)
from backend.app.modules.game_systems.schemas.game_rules import RulesProfile

_SYSTEMS = GameSystem.__table__
_DRAFTS = GameSystemMechanicDraft.__table__
_VERSIONS = GameSystemMechanicVersion.__table__


def _require_clean_session(session: AsyncSession) -> None:
    if session.new or session.dirty or session.deleted:
        raise RuntimeError(
            "Операция механики требует сессии "
            "без ожидающих ORM-изменений"
        )


def _mechanic_payload(value: dict[str, Any]) -> dict[str, Any]:
    """Проверить и нормализовать числовой профиль механики.

    Хранимый снимок остаётся в формате SystemMechanicContent
    (schema_version=1, без текстового раздела). Для проверки
    вычислимости профиль временно приводится к RulesProfile,
    который ожидает числовой контракт schema_version=4.
    """
    if not isinstance(value, dict):
        raise InvalidGameSystemRules("Механика должна быть объектом")

    try:
        mechanic = SystemMechanicContent.model_validate(value)
    except (ValueError, TypeError, KeyError) as exc:
        raise InvalidGameSystemRules(
            "Структура механики или её начальные значения недопустимы"
        ) from exc

    # Проверка вычислимости через серверный исполнитель формул.
    try:
        profile_dict = mechanic.model_dump(mode="python")
        profile_dict["schema_version"] = 4
        profile_dict["rulebook"] = {}
        validate_rules_profile(RulesProfile.model_validate(profile_dict))
    except ValueError as exc:
        raise InvalidGameSystemRules(
            "Механика не проходит проверку вычислимости"
        ) from exc

    # Возвращаем снимок в формате механики (schema_version=1).
    return mechanic.model_dump(mode="json")


def _draft_read(row: dict[str, Any]) -> GameSystemMechanicDraftRead:
    try:
        return GameSystemMechanicDraftRead.model_validate(dict(row))
    except ValueError as exc:
        raise GameSystemRulesStorageError(
            "Сохранённый черновик механики имеет неподдерживаемый формат"
        ) from exc


def _version_read(row: dict[str, Any]) -> GameSystemMechanicVersionRead:
    try:
        return GameSystemMechanicVersionRead.model_validate(dict(row))
    except ValueError as exc:
        raise GameSystemRulesStorageError(
            "Сохранённая публикация механики имеет неподдерживаемый формат"
        ) from exc


def _check_revision(row: dict[str, Any], expected_revision: int) -> None:
    if row["revision"] != expected_revision:
        raise GameSystemRulesConflict(
            "Черновик механики изменён. Получите актуальную ревизию"
        )


async def _get_system(
    session: AsyncSession,
    system_id: UUID,
    *,
    write: bool,
    active_only: bool = False,
) -> dict[str, Any]:
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
    return dict(system)


async def _find_mechanic_draft(
    session: AsyncSession,
    system_id: UUID,
    *,
    write: bool,
) -> dict[str, Any] | None:
    result = await session.execute(
        select(_DRAFTS)
        .where(_DRAFTS.c.system_id == system_id)
        .with_for_update(read=not write)
    )
    return result.mappings().one_or_none()


# ----------------------------------------------------------------------- #
# Состояние черновика механики
# ----------------------------------------------------------------------- #

async def get_mechanic_draft(
    session: AsyncSession,
    system_id: UUID,
) -> GameSystemMechanicDraftState:
    """Прочитать состояние черновика механики системы."""
    _require_clean_session(session)
    await _get_system(session, system_id, write=False)
    draft = await _find_mechanic_draft(session, system_id, write=False)
    return GameSystemMechanicDraftState(
        draft=None if draft is None else _draft_read(draft)
    )


# ----------------------------------------------------------------------- #
# Создание черновика механики
# ----------------------------------------------------------------------- #

async def create_mechanic_draft(
    session: AsyncSession,
    system_id: UUID,
    data: GameSystemMechanicDraftCreate,
) -> GameSystemMechanicDraftRead:
    """Создать черновик механики существующей системы."""
    data = GameSystemMechanicDraftCreate.model_validate(
        data.model_dump(mode="python")
    )
    payload = _mechanic_payload(data.mechanic.model_dump(mode="json"))
    _require_clean_session(session)

    await _get_system(session, system_id, write=True)
    existing = await _find_mechanic_draft(session, system_id, write=True)

    if existing is not None:
        raise GameSystemRulesConflict("Черновик механики уже существует")

    result = await session.execute(
        insert(_DRAFTS)
        .values(
            system_id=system_id,
            mechanic_json=payload,
            revision=1,
            is_published=False,
        )
        .returning(*_DRAFTS.c)
    )
    return _draft_read(result.mappings().one())


# ----------------------------------------------------------------------- #
# Обновление черновика механики
# ----------------------------------------------------------------------- #

async def update_mechanic_draft(
    session: AsyncSession,
    system_id: UUID,
    data: GameSystemMechanicDraftUpdate,
) -> GameSystemMechanicDraftRead:
    """Заменить механику черновика с проверкой ревизии."""
    data = GameSystemMechanicDraftUpdate.model_validate(
        data.model_dump(mode="python")
    )
    payload = _mechanic_payload(data.mechanic.model_dump(mode="json"))
    _require_clean_session(session)

    await _get_system(session, system_id, write=True)
    draft = await _find_mechanic_draft(session, system_id, write=True)

    if draft is None:
        raise GameSystemRulesConflict("Черновик механики отсутствует")

    _check_revision(draft, data.expected_revision)

    result = await session.execute(
        update(_DRAFTS)
        .where(
            _DRAFTS.c.id == draft["id"],
            _DRAFTS.c.revision == data.expected_revision,
        )
        .values(
            mechanic_json=payload,
            revision=_DRAFTS.c.revision + 1,
            updated_at=func.now(),
        )
        .returning(*_DRAFTS.c)
    )
    saved = result.mappings().one_or_none()

    if saved is None:
        raise GameSystemRulesConflict(
            "Черновик механики изменился во время сохранения"
        )

    return _draft_read(saved)


# ----------------------------------------------------------------------- #
# Публикация версии механики
# ----------------------------------------------------------------------- #

async def publish_mechanic_version(
    session: AsyncSession,
    system_id: UUID,
    data: GameSystemMechanicPublish,
) -> GameSystemMechanicVersionRead:
    """Опубликовать черновик механики как версию."""
    data = GameSystemMechanicPublish.model_validate(
        data.model_dump(mode="python")
    )
    _require_clean_session(session)

    system = await _get_system(session, system_id, write=True)

    draft = await _find_mechanic_draft(session, system_id, write=True)

    if draft is None:
        raise GameSystemRulesConflict("Для публикации нужен черновик механики")

    _check_revision(draft, data.expected_revision)

    raw_mechanic = draft["mechanic_json"]
    if not isinstance(raw_mechanic, dict):
        raise GameSystemRulesConflict("Исправьте формат черновика перед публикацией")

    payload = _mechanic_payload(raw_mechanic)

    # Берём версию движка из карточки системы.
    rules_engine_version = system.get("rules_engine_version", "1.0.0")

    # Номер следующей версии.
    number_result = await session.execute(
        select(
            func.coalesce(func.max(_VERSIONS.c.version_number), 0) + 1
        )
        .where(_VERSIONS.c.system_id == system_id)
    )
    next_number = number_result.scalar_one()

    # Создаём версию.
    # JSONB превращает Python None в JSON null, а не в SQL NULL, поэтому
    # поля происхождения добавляются только когда основа выбрана.
    version_values = {
        "system_id": system_id,
        "version_number": next_number,
        "source_draft_revision": data.expected_revision,
        "mechanic_json": payload,
        "rules_engine_version": rules_engine_version,
    }

    if draft.get("engine_version_id") is not None:
        version_values["engine_version_id"] = draft.get("engine_version_id")
        version_values["mechanic_overrides_json"] = draft.get("mechanic_overrides_json")

    version_result = await session.execute(
        insert(_VERSIONS)
        .values(**version_values)
        .returning(*_VERSIONS.c)
    )
    response = _version_read(version_result.mappings().one())

    # Потребляем ревизию черновика (инкремент, помечаем как опубликованный).
    await session.execute(
        update(_DRAFTS)
        .where(
            _DRAFTS.c.id == draft["id"],
            _DRAFTS.c.revision == data.expected_revision,
        )
        .values(
            is_published=True,
            revision=_DRAFTS.c.revision + 1,
            updated_at=func.now(),
        )
    )

    return response


# ----------------------------------------------------------------------- #
# Чтение опубликованных версий механики
# ----------------------------------------------------------------------- #

async def get_latest_mechanic_version(
    session: AsyncSession,
    system_id: UUID,
    *,
    active_only: bool = True,
) -> GameSystemMechanicVersionRead | None:
    """Последняя публикация механики для системы."""
    _require_clean_session(session)
    await _get_system(session, system_id, write=False, active_only=active_only)

    result = await session.execute(
        select(_VERSIONS)
        .where(_VERSIONS.c.system_id == system_id)
        .order_by(_VERSIONS.c.version_number.desc())
        .limit(1)
    )
    row = result.mappings().one_or_none()
    return None if row is None else _version_read(row)


async def get_mechanic_version(
    session: AsyncSession,
    system_id: UUID,
    version_id: UUID,
    *,
    active_only: bool = True,
) -> GameSystemMechanicVersionRead:
    """Прочитать конкретную версию механики."""
    _require_clean_session(session)
    await _get_system(session, system_id, write=False, active_only=active_only)

    result = await session.execute(
        select(_VERSIONS)
        .where(
            _VERSIONS.c.system_id == system_id,
            _VERSIONS.c.id == version_id,
        )
    )
    row = result.mappings().one_or_none()
    if row is None:
        raise GameSystemNotFound("Версия механики не найдена")
    return _version_read(row)


async def list_mechanic_versions(
    session: AsyncSession,
    system_id: UUID,
    *,
    active_only: bool = True,
    limit: int = 20,
    before: int | None = None,
) -> GameSystemMechanicVersionPage:
    """Пагинированный список версий механики (по номеру)."""
    _require_clean_session(session)
    await _get_system(session, system_id, write=False, active_only=active_only)

    query = select(_VERSIONS).where(
        _VERSIONS.c.system_id == system_id
    )
    if before is not None:
        query = query.where(_VERSIONS.c.version_number < before)
    query = query.order_by(_VERSIONS.c.version_number.desc()).limit(limit)

    result = await session.execute(query)
    rows = result.mappings().all()

    next_before = None
    if len(rows) == limit:
        next_before = rows[-1]["version_number"] - 1 if rows[-1]["version_number"] > 1 else None

    return GameSystemMechanicVersionPage(
        items=[_version_read(row) for row in rows],
        next_before=next_before,
    )
