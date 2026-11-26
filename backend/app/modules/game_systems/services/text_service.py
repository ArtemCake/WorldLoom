# backend/app/modules/game_systems/services/text_service.py

"""Черновики и публикации текстовых правил системы.

Сервис оперирует таблицами `game_system_text_drafts` и
`game_system_text_versions`. Все операции используют
`text_json` как раздел rulebook (главы, поля).

Текстовые правила не содержат формул — только описания.
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
)
from backend.app.modules.game_systems.models.game_systems import GameSystem
from backend.app.modules.game_systems.models.system_versions import (
    GameSystemTextDraft,
    GameSystemTextVersion,
)
from backend.app.modules.game_systems.schemas.game_system_versions import (
    SystemTextContent,
    GameSystemTextDraftCreate,
    GameSystemTextDraftRead,
    GameSystemTextDraftState,
    GameSystemTextDraftUpdate,
    GameSystemTextPublish,
    GameSystemTextVersionPage,
    GameSystemTextVersionRead,
)

_SYSTEMS = GameSystem.__table__
_DRAFTS = GameSystemTextDraft.__table__
_VERSIONS = GameSystemTextVersion.__table__


def _require_clean_session(session: AsyncSession) -> None:
    if session.new or session.dirty or session.deleted:
        raise RuntimeError(
            "Операция текстовых правил требует сессии "
            "без ожидающих ORM-изменений"
        )


def _text_payload(value: dict[str, Any]) -> dict[str, Any]:
    """Проверить и нормализовать текстовые правила системы."""
    if not isinstance(value, dict):
        raise GameSystemRulesConflict("Текст должен быть объектом")

    try:
        validated = SystemTextContent.model_validate(value)
        return validated.model_dump(mode="json")
    except (ValueError, TypeError, KeyError) as exc:
        raise GameSystemRulesConflict(
            "Структура текстовых правил недопустима"
        ) from exc


def _draft_read(row: dict[str, Any]) -> GameSystemTextDraftRead:
    try:
        return GameSystemTextDraftRead.model_validate(dict(row))
    except ValueError as exc:
        raise GameSystemRulesStorageError(
            "Сохранённый черновик текста имеет неподдерживаемый формат"
        ) from exc


def _version_read(row: dict[str, Any]) -> GameSystemTextVersionRead:
    try:
        return GameSystemTextVersionRead.model_validate(dict(row))
    except ValueError as exc:
        raise GameSystemRulesStorageError(
            "Сохранённая публикация текста имеет неподдерживаемый формат"
        ) from exc


def _check_revision(row: dict[str, Any], expected_revision: int) -> None:
    if row["revision"] != expected_revision:
        raise GameSystemRulesConflict(
            "Черновик текста изменён. Получите актуальную ревизию"
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


async def _find_text_draft(
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
# Состояние черновика текста
# ----------------------------------------------------------------------- #

async def get_text_draft(
    session: AsyncSession,
    system_id: UUID,
) -> GameSystemTextDraftState:
    """Прочитать состояние черновика текстовых правил системы."""
    _require_clean_session(session)
    await _get_system(session, system_id, write=False)
    draft = await _find_text_draft(session, system_id, write=False)
    return GameSystemTextDraftState(
        draft=None if draft is None else _draft_read(draft)
    )


# ----------------------------------------------------------------------- #
# Создание черновика текста
# ----------------------------------------------------------------------- #

async def create_text_draft(
    session: AsyncSession,
    system_id: UUID,
    data: GameSystemTextDraftCreate,
) -> GameSystemTextDraftRead:
    """Создать черновик текстовых правил существующей системы."""
    data = GameSystemTextDraftCreate.model_validate(
        data.model_dump(mode="python")
    )
    payload = _text_payload(data.text.model_dump(mode="json"))
    _require_clean_session(session)

    await _get_system(session, system_id, write=True)
    existing = await _find_text_draft(session, system_id, write=True)

    if existing is not None:
        raise GameSystemRulesConflict("Черновик текстовых правил уже существует")

    result = await session.execute(
        insert(_DRAFTS)
        .values(
            system_id=system_id,
            text_json=payload,
            revision=1,
            is_published=False,
        )
        .returning(*_DRAFTS.c)
    )
    return _draft_read(result.mappings().one())


# ----------------------------------------------------------------------- #
# Обновление черновика текста
# ----------------------------------------------------------------------- #

async def update_text_draft(
    session: AsyncSession,
    system_id: UUID,
    data: GameSystemTextDraftUpdate,
) -> GameSystemTextDraftRead:
    """Заменить текст черновика с проверкой ревизии."""
    data = GameSystemTextDraftUpdate.model_validate(
        data.model_dump(mode="python")
    )
    payload = _text_payload(data.text.model_dump(mode="json"))
    _require_clean_session(session)

    await _get_system(session, system_id, write=True)
    draft = await _find_text_draft(session, system_id, write=True)

    if draft is None:
        raise GameSystemRulesConflict("Черновик текстовых правил отсутствует")

    _check_revision(draft, data.expected_revision)

    result = await session.execute(
        update(_DRAFTS)
        .where(
            _DRAFTS.c.id == draft["id"],
            _DRAFTS.c.revision == data.expected_revision,
        )
        .values(
            text_json=payload,
            revision=_DRAFTS.c.revision + 1,
            updated_at=func.now(),
        )
        .returning(*_DRAFTS.c)
    )
    saved = result.mappings().one_or_none()

    if saved is None:
        raise GameSystemRulesConflict(
            "Черновик текста изменился во время сохранения"
        )

    return _draft_read(saved)


# ----------------------------------------------------------------------- #
# Публикация версии текстовых правил
# ----------------------------------------------------------------------- #

async def publish_text_version(
    session: AsyncSession,
    system_id: UUID,
    data: GameSystemTextPublish,
) -> GameSystemTextVersionRead:
    """Опубликовать черновик текста как версию."""
    data = GameSystemTextPublish.model_validate(
        data.model_dump(mode="python")
    )
    _require_clean_session(session)

    system = await _get_system(session, system_id, write=True)

    draft = await _find_text_draft(session, system_id, write=True)

    if draft is None:
        raise GameSystemRulesConflict("Для публикации нужен черновик текста")

    _check_revision(draft, data.expected_revision)

    raw_text = draft["text_json"]
    if not isinstance(raw_text, dict):
        raise GameSystemRulesConflict("Исправьте формат черновика перед публикацией")

    payload = _text_payload(raw_text)

    # Номер следующей версии.
    number_result = await session.execute(
        select(
            func.coalesce(func.max(_VERSIONS.c.version_number), 0) + 1
        )
        .where(_VERSIONS.c.system_id == system_id)
    )
    next_number = number_result.scalar_one()

    # Создаём версию текста.
    version_result = await session.execute(
        insert(_VERSIONS)
        .values(
            system_id=system_id,
            version_number=next_number,
            source_draft_revision=data.expected_revision,
            text_json=payload,
        )
        .returning(*_VERSIONS.c)
    )
    response = _version_read(version_result.mappings().one())

    # Потребляем ревизию черновика.
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
# Чтение опубликованных версий текста
# ----------------------------------------------------------------------- #

async def get_latest_text_version(
    session: AsyncSession,
    system_id: UUID,
    *,
    active_only: bool = True,
) -> GameSystemTextVersionRead | None:
    """Последняя публикация текста для системы."""
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


async def get_text_version(
    session: AsyncSession,
    system_id: UUID,
    version_id: UUID,
    *,
    active_only: bool = True,
) -> GameSystemTextVersionRead:
    """Прочитать конкретную версию текста."""
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
        raise GameSystemNotFound("Версия текста не найдена")
    return _version_read(row)


async def list_text_versions(
    session: AsyncSession,
    system_id: UUID,
    *,
    active_only: bool = True,
    limit: int = 20,
    before: int | None = None,
) -> GameSystemTextVersionPage:
    """Пагинированный список версий текста (по номеру)."""
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

    return GameSystemTextVersionPage(
        items=[_version_read(row) for row in rows],
        next_before=next_before,
    )
