# backend/app/modules/game_systems/services/version_service.py

"""Сборка комплекта системы и привязка текущей версии.

Комплект (GameSystemVersion) связывает:
- опубликованную версию текстовых правил (опционально);
- опубликованную версию механики (обязательно).

Публикация комплекта:
1. Создаёт версию текста (если есть черновик и указана ревизия).
2. Создаёт версию механики (если есть черновик и указана ревизия).
3. Связывает их в комплект.
4. Привязывает комплект к системе как current_version.

Если черновик текста/механики не передан или ревизия не указана,
соответствующая версия берётся из последнего опубликованного снимка.
"""

from __future__ import annotations
from datetime import datetime, timezone
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
    GameSystemMechanicDraft,
    GameSystemMechanicVersion,
    GameSystemTextDraft,
    GameSystemTextVersion,
    GameSystemVersion,
)
from backend.app.modules.game_systems.rules.mechanic_codec import mechanic_to_profile
from backend.app.modules.game_systems.schemas.game_rules import RulesProfile
from backend.app.modules.game_systems.schemas.game_system_versions import (
    GameSystemCurrentVersionState,
    GameSystemPublishedDocument,
    GameSystemPublishedDocumentState,
    GameSystemVersionBind,
    GameSystemVersionPublish,
    GameSystemVersionRead,
    GameSystemVersionSummary,
    GameSystemVersionPage,
)

_SYSTEMS = GameSystem.__table__
_TEXT_DRAFTS = GameSystemTextDraft.__table__
_MECHANIC_DRAFTS = GameSystemMechanicDraft.__table__
_TEXT_VERSIONS = GameSystemTextVersion.__table__
_MECHANIC_VERSIONS = GameSystemMechanicVersion.__table__
_SYSTEM_VERSIONS = GameSystemVersion.__table__


def _require_clean_session(session: AsyncSession) -> None:
    if session.new or session.dirty or session.deleted:
        raise RuntimeError(
            "Операция комплекта требует сессии "
            "без ожидающих ORM-изменений"
        )


def _system_version_read(row: dict[str, Any]) -> GameSystemVersionRead:
    try:
        return GameSystemVersionRead.model_validate(dict(row))
    except ValueError as exc:
        raise GameSystemRulesStorageError(
            "Сохранённый комплект имеет неподдерживаемый формат"
        ) from exc


def _system_version_summary(row: dict[str, Any]) -> GameSystemVersionSummary:
    try:
        return GameSystemVersionSummary.model_validate(dict(row))
    except ValueError as exc:
        raise GameSystemRulesStorageError(
            "Комплект имеет неподдерживаемый формат"
        ) from exc


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
        select(_TEXT_DRAFTS)
        .where(_TEXT_DRAFTS.c.system_id == system_id)
        .with_for_update(read=not write)
    )
    return result.mappings().one_or_none()


async def _find_mechanic_draft(
    session: AsyncSession,
    system_id: UUID,
    *,
    write: bool,
) -> dict[str, Any] | None:
    result = await session.execute(
        select(_MECHANIC_DRAFTS)
        .where(_MECHANIC_DRAFTS.c.system_id == system_id)
        .with_for_update(read=not write)
    )
    return result.mappings().one_or_none()


def _check_revision(row: dict[str, Any], expected_revision: int) -> None:
    if row["revision"] != expected_revision:
        raise GameSystemRulesConflict(
            "Черновик изменён. Получите актуальную ревизию"
        )


# ----------------------------------------------------------------------- #
# Сборка комплекта (публикация версии системы)
# ----------------------------------------------------------------------- #

async def publish_system_version(
    session: AsyncSession,
    system_id: UUID,
    data: GameSystemVersionPublish,
) -> GameSystemVersionRead:
    """Собрать версию системы из актуальных черновиков текста и механики.

    Алгоритм:
    1. Проверить наличие и ревизию черновика текста (если expected_text_revision указан).
    2. Проверить наличие и ревизию черновика механики (если expected_mechanic_revision указан).
    3. Опубликовать версии текста и механики из черновиков.
    4. Если черновик не найден или ревизия не указана — взять последнюю опубликованную версию.
    5. Связать версии в комплект.
    6. Привязать комплект к системе как current_version.
    """
    data = GameSystemVersionPublish.model_validate(
        data.model_dump(mode="python")
    )
    _require_clean_session(session)

    system = await _get_system(session, system_id, write=True)

    text_version_id: UUID | None = None
    mechanic_version_id: UUID | None = None

    # ------------------------------------------------------------------- #
    # Текст
    # ------------------------------------------------------------------- #
    if data.expected_text_revision is not None:
        text_draft = await _find_text_draft(session, system_id, write=True)
        if text_draft is None:
            raise GameSystemRulesConflict("Для публикации комплекта нужен черновик текста")
        _check_revision(text_draft, data.expected_text_revision)

        # Публикуем версию текста.
        text_payload = text_draft["text_json"]
        if not isinstance(text_payload, dict):
            raise GameSystemRulesConflict("Исправьте формат черновика текста перед публикацией")

        number_result = await session.execute(
            select(
                func.coalesce(func.max(_TEXT_VERSIONS.c.version_number), 0) + 1
            )
            .where(_TEXT_VERSIONS.c.system_id == system_id)
        )
        next_number = number_result.scalar_one()

        version_result = await session.execute(
            insert(_TEXT_VERSIONS)
            .values(
                system_id=system_id,
                version_number=next_number,
                source_draft_revision=data.expected_text_revision,
                text_json=text_payload,
            )
            .returning(*_TEXT_VERSIONS.c)
        )
        text_version_id = version_result.mappings().one()["id"]

        # Потребляем ревизию черновика.
        await session.execute(
            update(_TEXT_DRAFTS)
            .where(
                _TEXT_DRAFTS.c.id == text_draft["id"],
                _TEXT_DRAFTS.c.revision == data.expected_text_revision,
            )
            .values(
                is_published=True,
                revision=_TEXT_DRAFTS.c.revision + 1,
                updated_at=func.now(),
            )
        )
    else:
        # Берём последнюю опубликованную версию текста.
        result = await session.execute(
            select(_TEXT_VERSIONS)
            .where(_TEXT_VERSIONS.c.system_id == system_id)
            .order_by(_TEXT_VERSIONS.c.version_number.desc())
            .limit(1)
        )
        row = result.mappings().one_or_none()
        if row is not None:
            text_version_id = row["id"]

    # ------------------------------------------------------------------- #
    # Механика
    # ------------------------------------------------------------------- #
    if data.expected_mechanic_revision is not None:
        mechanic_draft = await _find_mechanic_draft(session, system_id, write=True)
        if mechanic_draft is None:
            raise GameSystemRulesConflict("Для публикации комплекта нужен черновик механики")
        _check_revision(mechanic_draft, data.expected_mechanic_revision)

        mechanic_payload = mechanic_draft["mechanic_json"]
        if not isinstance(mechanic_payload, dict):
            raise GameSystemRulesConflict("Исправьте формат черновика механики перед публикацией")

        # Берём версию движка из карточки системы.
        rules_engine_version = system.get("rules_engine_version", "1.0.0")

        number_result = await session.execute(
            select(
                func.coalesce(func.max(_MECHANIC_VERSIONS.c.version_number), 0) + 1
            )
            .where(_MECHANIC_VERSIONS.c.system_id == system_id)
        )
        next_number = number_result.scalar_one()

        version_values = {
            "system_id": system_id,
            "version_number": next_number,
            "source_draft_revision": data.expected_mechanic_revision,
            "mechanic_json": mechanic_payload,
            "rules_engine_version": rules_engine_version,
        }

        # JSONB превращает None в JSON null, а не в SQL NULL, поэтому
        # происхождение добавляется только при выбранной основе.
        if mechanic_draft.get("engine_version_id") is not None:
            version_values["engine_version_id"] = mechanic_draft.get("engine_version_id")
            version_values["mechanic_overrides_json"] = mechanic_draft.get("mechanic_overrides_json")

        version_result = await session.execute(
            insert(_MECHANIC_VERSIONS)
            .values(**version_values)
            .returning(*_MECHANIC_VERSIONS.c)
        )
        mechanic_version_id = version_result.mappings().one()["id"]

        # Потребляем ревизию черновика.
        await session.execute(
            update(_MECHANIC_DRAFTS)
            .where(
                _MECHANIC_DRAFTS.c.id == mechanic_draft["id"],
                _MECHANIC_DRAFTS.c.revision == data.expected_mechanic_revision,
            )
            .values(
                is_published=True,
                revision=_MECHANIC_DRAFTS.c.revision + 1,
                updated_at=func.now(),
            )
        )
    else:
        # Берём последнюю опубликованную версию механики.
        result = await session.execute(
            select(_MECHANIC_VERSIONS)
            .where(_MECHANIC_VERSIONS.c.system_id == system_id)
            .order_by(_MECHANIC_VERSIONS.c.version_number.desc())
            .limit(1)
        )
        row = result.mappings().one_or_none()
        if row is None:
            raise GameSystemRulesConflict(
                "Не указана ревизия черновика механики и нет опубликованной версии"
            )
        mechanic_version_id = row["id"]

    # ------------------------------------------------------------------- #
    # Создаём комплект
    # ------------------------------------------------------------------- #
    number_result = await session.execute(
        select(
            func.coalesce(func.max(_SYSTEM_VERSIONS.c.version_number), 0) + 1
        )
        .where(_SYSTEM_VERSIONS.c.system_id == system_id)
    )
    next_number = number_result.scalar_one()

    version_result = await session.execute(
        insert(_SYSTEM_VERSIONS)
        .values(
            system_id=system_id,
            version_number=next_number,
            text_version_id=text_version_id,
            mechanic_version_id=mechanic_version_id,
            published_at=datetime.now(timezone.utc),
        )
        .returning(*_SYSTEM_VERSIONS.c)
    )
    response = _system_version_read(version_result.mappings().one())

    # ------------------------------------------------------------------- #
    # Привязываем текущую версию
    # ------------------------------------------------------------------- #
    await session.execute(
        update(_SYSTEMS)
        .where(_SYSTEMS.c.id == system_id)
        .values(current_version_id=response["id"])
    )

    return response


# ----------------------------------------------------------------------- #
# Привязка текущей версии системы (прямая привязка существующего комплекта)
# ----------------------------------------------------------------------- #

async def bind_current_version(
    session: AsyncSession,
    system_id: UUID,
    data: GameSystemVersionBind,
) -> GameSystemVersionRead:
    """Закрепить существующий комплект как текущую версию системы."""
    data = GameSystemVersionBind.model_validate(
        data.model_dump(mode="python")
    )
    _require_clean_session(session)

    system = await _get_system(session, system_id, write=True)

    # Проверяем, что version_id существует и принадлежит системе.
    version_result = await session.execute(
        select(_SYSTEM_VERSIONS)
        .where(
            _SYSTEM_VERSIONS.c.system_id == system_id,
            _SYSTEM_VERSIONS.c.id == data.version_id,
        )
    )
    version_row = version_result.mappings().one_or_none()
    if version_row is None:
        raise GameSystemNotFound("Комплект не найден")

    # Проверяем ожидаемую версию (если не null).
    current_version_id = system.get("current_version_id")
    if data.expected_version_id is not None:
        if current_version_id != data.expected_version_id:
            raise GameSystemRulesConflict(
                "Текущая версия системы изменилась. Получите актуальное состояние"
            )

    # Привязываем.
    await session.execute(
        update(_SYSTEMS)
        .where(_SYSTEMS.c.id == system_id)
        .values(current_version_id=data.version_id)
    )

    return _system_version_read(version_row)


# ----------------------------------------------------------------------- #
# Состояние текущей версии
# ----------------------------------------------------------------------- #

async def get_current_version_state(
    session: AsyncSession,
    system_id: UUID,
) -> GameSystemCurrentVersionState:
    """Прочитать текущую привязанную версию системы."""
    _require_clean_session(session)
    await _get_system(session, system_id, write=False)

    result = await session.execute(
        select(_SYSTEMS.c.current_version_id)
        .where(_SYSTEMS.c.id == system_id)
    )
    current_version_id = result.scalar_one_or_none()

    if current_version_id is None:
        return GameSystemCurrentVersionState(version=None)

    result = await session.execute(
        select(_SYSTEM_VERSIONS)
        .where(_SYSTEM_VERSIONS.c.id == current_version_id)
    )
    row = result.mappings().one_or_none()
    if row is None:
        return GameSystemCurrentVersionState(version=None)

    return GameSystemCurrentVersionState(
        version=_system_version_read(row)
    )


# ----------------------------------------------------------------------- #
# Список версий системы
# ----------------------------------------------------------------------- #

async def get_system_version(
    session: AsyncSession,
    system_id: UUID,
    version_id: UUID,
    *,
    active_only: bool = True,
) -> GameSystemVersionRead:
    """Прочитать конкретный комплект указанной системы."""
    _require_clean_session(session)
    await _get_system(session, system_id, write=False, active_only=active_only)

    result = await session.execute(
        select(_SYSTEM_VERSIONS)
        .where(
            _SYSTEM_VERSIONS.c.system_id == system_id,
            _SYSTEM_VERSIONS.c.id == version_id,
        )
    )
    row = result.mappings().one_or_none()
    if row is None:
        raise GameSystemNotFound("Комплект не найден")
    return _system_version_read(row)


async def list_system_versions(
    session: AsyncSession,
    system_id: UUID,
    *,
    active_only: bool = True,
    limit: int = 20,
    before: int | None = None,
) -> GameSystemVersionPage:
    """Пагинированный список версий системы (комплектов).

    Номер исполнителя берётся из составной версии механики:
    комплект наследует числовую основу, а не задаёт её сам.
    """
    _require_clean_session(session)
    await _get_system(session, system_id, write=False, active_only=active_only)

    query = (
        select(
            *_SYSTEM_VERSIONS.c,
            _MECHANIC_VERSIONS.c.rules_engine_version,
        )
        .select_from(
            _SYSTEM_VERSIONS.join(
                _MECHANIC_VERSIONS,
                _MECHANIC_VERSIONS.c.id
                == _SYSTEM_VERSIONS.c.mechanic_version_id,
            )
        )
        .where(_SYSTEM_VERSIONS.c.system_id == system_id)
    )
    if before is not None:
        query = query.where(_SYSTEM_VERSIONS.c.version_number < before)
    query = query.order_by(_SYSTEM_VERSIONS.c.version_number.desc()).limit(limit)

    result = await session.execute(query)
    rows = result.mappings().all()

    next_before = None
    if len(rows) == limit:
        next_before = rows[-1]["version_number"] - 1 if rows[-1]["version_number"] > 1 else None

    return GameSystemVersionPage(
        items=[_system_version_summary(row) for row in rows],
        next_before=next_before,
    )


# ----------------------------------------------------------------------- #
# Собранный документ опубликованной версии
# ----------------------------------------------------------------------- #

async def _load_document(
    session: AsyncSession,
    system: dict[str, Any],
    version_row: dict[str, Any],
) -> GameSystemPublishedDocument:
    """Соединить комплект с его версией механики и версией текста.

    Числовая основа обязательна: без неё лист не вычисляется.
    Текстовая версия необязательна: тогда главы остаются пустыми.
    """
    mechanic_result = await session.execute(
        select(_MECHANIC_VERSIONS)
        .where(_MECHANIC_VERSIONS.c.id == version_row["mechanic_version_id"])
    )
    mechanic_row = mechanic_result.mappings().one_or_none()

    if mechanic_row is None:
        raise GameSystemRulesStorageError(
            "Версия механики комплекта не найдена"
        )

    chapters: dict[str, Any] = {}

    if version_row["text_version_id"] is not None:
        text_result = await session.execute(
            select(_TEXT_VERSIONS)
            .where(_TEXT_VERSIONS.c.id == version_row["text_version_id"])
        )
        text_row = text_result.mappings().one_or_none()

        if text_row is None:
            raise GameSystemRulesStorageError(
                "Версия текстовых правил комплекта не найдена"
            )

        text_json = text_row["text_json"]

        if not isinstance(text_json, dict):
            raise GameSystemRulesStorageError(
                "Версия текстовых правил имеет неподдерживаемый формат"
            )

        received = text_json.get("chapters")

        if isinstance(received, dict):
            chapters = received

    mechanic_json = mechanic_row["mechanic_json"]

    if not isinstance(mechanic_json, dict):
        raise GameSystemRulesStorageError(
            "Версия механики имеет неподдерживаемый формат"
        )

    try:
        profile = RulesProfile.model_validate(
            {**mechanic_to_profile(mechanic_json), "rulebook": chapters}
        )
    except ValueError as exc:
        raise GameSystemRulesStorageError(
            "Сохранённый комплект не собирается в профиль правил"
        ) from exc

    return GameSystemPublishedDocument(
        version=_system_version_read(version_row),
        rules=profile,
        rules_engine_version=mechanic_row["rules_engine_version"],
    )


async def get_published_document(
    session: AsyncSession,
    system_id: UUID,
    version_id: UUID | None = None,
    *,
    active_only: bool = True,
) -> GameSystemPublishedDocumentState:
    """Собрать документ опубликованной версии системы.

    Без version_id берётся текущий комплект системы; если он не привязан
    или удалён — возвращается пустое состояние.
    """
    _require_clean_session(session)
    system = await _get_system(
        session,
        system_id,
        write=False,
        active_only=active_only,
    )

    if version_id is None:
        version_id = system.get("current_version_id")

        if version_id is None:
            return GameSystemPublishedDocumentState(document=None)

    result = await session.execute(
        select(_SYSTEM_VERSIONS)
        .where(
            _SYSTEM_VERSIONS.c.id == version_id,
            _SYSTEM_VERSIONS.c.system_id == system_id,
        )
    )
    version_row = result.mappings().one_or_none()

    if version_row is None:
        return GameSystemPublishedDocumentState(document=None)

    return GameSystemPublishedDocumentState(
        document=await _load_document(session, system, dict(version_row))
    )
