# backend/app/modules/rules/services/workspace_overview.py

"""Read-only обзор рабочего пространства системы (§5.1).

Агрегирует паспорт системы, черновик механики, черновик текста,
основу и книги без модификации данных.

Транзакцией управляет вызывающий слой.
"""

from __future__ import annotations
from uuid import UUID
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.modules.game_systems.errors import GameSystemNotFound
from backend.app.modules.game_systems.models.game_systems import GameSystem
from backend.app.modules.game_systems.models.system_versions import (
    GameSystemMechanicDraft,
    GameSystemVersion,
)
from backend.app.modules.game_systems.rules.mechanic_codec import (
    mechanic_to_profile,
)
from backend.app.modules.rules.models.books import RuleBook, RuleBookDraft, RuleBookVersion
from backend.app.modules.rules.schemas.workspace_overview import (
    WorkspaceBookSummary,
    WorkspaceEngineOrigin,
    WorkspaceOverview,
    WorkspaceRulesDraft,
    WorkspaceRulesOverview,
    WorkspaceSystemPassport,
)


_SYSTEMS = GameSystem.__table__
_MECHANIC_DRAFTS = GameSystemMechanicDraft.__table__
_SYSTEM_VERSIONS = GameSystemVersion.__table__
_BOOKS = RuleBook.__table__
_BOOK_DRAFTS = RuleBookDraft.__table__
_BOOK_VERSIONS = RuleBookVersion.__table__


def _make_engine_origin(draft: dict) -> WorkspaceEngineOrigin | None:
    """Собрать происхождение черновика из engine_version_id + overrides."""
    if draft is None or draft["engine_version_id"] is None:
        return None
    return WorkspaceEngineOrigin(
        engine_version_id=draft["engine_version_id"],
        rules_overrides_json=draft.get("mechanic_overrides_json") or {},
    )


async def get_workspace_overview(
    session: AsyncSession,
    system_id: UUID,
) -> WorkspaceOverview:
    """Собрать read-only обзор рабочего пространства системы."""

    # 1. Паспорт системы
    system_row = (
        await session.execute(
            select(_SYSTEMS).where(_SYSTEMS.c.id == system_id)
        )
    ).mappings().one_or_none()

    if system_row is None:
        raise GameSystemNotFound("Игровая система не найдена")

    system = WorkspaceSystemPassport(
        id=system_row["id"],
        name=system_row["name"],
        slug=system_row["slug"],
        description=system_row["description"],
        is_active=system_row["is_active"],
        rules_engine_version=system_row["rules_engine_version"],
        current_rules_version_id=system_row.get("current_version_id"),
        created_at=system_row["created_at"],
        updated_at=system_row["updated_at"],
    )

    # 2. Черновик механики + основа механики
    mechanic_draft = (
        await session.execute(
            select(_MECHANIC_DRAFTS).where(_MECHANIC_DRAFTS.c.system_id == system_id)
        )
    ).mappings().one_or_none()

    draft = None
    engine = None

    if mechanic_draft is not None:
        # Собираем rules_json из mechanic_json для обратной совместимости
        mechanic_json = mechanic_draft.get("mechanic_json") or {}
        rules_json = mechanic_to_profile(mechanic_json)

        draft = WorkspaceRulesDraft(
            id=mechanic_draft["id"],
            system_id=mechanic_draft["system_id"],
            revision=mechanic_draft["revision"],
            rules_json=rules_json,
            created_at=mechanic_draft["created_at"],
            updated_at=mechanic_draft["updated_at"],
        )

        engine = _make_engine_origin(dict(mechanic_draft))

    rules = WorkspaceRulesOverview(draft=draft, engine=engine)

    # 3. Книги системы + последняя публикация
    max_version = (
        select(
            _BOOK_VERSIONS.c.book_id.label("book_id"),
            func.max(_BOOK_VERSIONS.c.version_number).label("max_version"),
        )
        .group_by(_BOOK_VERSIONS.c.book_id)
        .subquery()
    )

    books_stmt = (
        select(
            _BOOKS.c.id.label("book_id"),
            _BOOKS.c.slug.label("slug"),
            _BOOK_VERSIONS.c.version_number.label("latest_version"),
            _BOOK_VERSIONS.c.published_at.label("latest_published_at"),
            _BOOK_VERSIONS.c.id.label("version_id"),
            _BOOK_VERSIONS.c.content_json.label("content_json"),
        )
        .select_from(
            _BOOKS.outerjoin(max_version, max_version.c.book_id == _BOOKS.c.id)
            .outerjoin(
                _BOOK_VERSIONS,
                and_(
                    _BOOK_VERSIONS.c.book_id == _BOOKS.c.id,
                    _BOOK_VERSIONS.c.version_number == max_version.c.max_version,
                ),
            )
        )
        .where(_BOOKS.c.system_id == system_id)
        .order_by(_BOOKS.c.id)
    )

    book_rows = (await session.execute(books_stmt)).mappings().all()

    # Загружаем title из черновиков для всех книг (fallback)
    titles: dict[UUID, str] = {}
    if book_rows:
        draft_stmt = (
            select(_BOOK_DRAFTS.c.book_id, _BOOK_DRAFTS.c.content_json)
            .where(_BOOK_DRAFTS.c.book_id.in_([row["book_id"] for row in book_rows]))
        )
        for row in (await session.execute(draft_stmt)).mappings().all():
            content = row["content_json"]
            title = content.get("title") if isinstance(content, dict) else None
            if isinstance(title, str) and title.strip():
                titles[row["book_id"]] = title

    books: list[WorkspaceBookSummary] = []
    books_published = 0

    for row in book_rows:
        latest_version = row["latest_version"]
        published_title = None
        if isinstance(row["content_json"], dict):
            published_title = row["content_json"].get("title")

        if published_title and isinstance(published_title, str) and published_title.strip():
            title = published_title
        else:
            title = titles.get(row["book_id"], row["slug"])

        if latest_version is not None:
            books_published += 1

        books.append(WorkspaceBookSummary(
            book_id=row["book_id"],
            slug=row["slug"],
            title=title,
            latest_version=latest_version,
            latest_published_at=row["latest_published_at"],
            version_id=row["version_id"],
            content_json=row["content_json"] if isinstance(row["content_json"], dict) else None,
            is_published=latest_version is not None,
        ))

    # 4. Опубликована ли система + UUID последней версии (через комплект)
    version_id = None
    has_published = (
        await session.execute(
            select(_SYSTEM_VERSIONS.c.id)
            .where(_SYSTEM_VERSIONS.c.system_id == system_id)
            .order_by(_SYSTEM_VERSIONS.c.version_number.desc())
            .limit(1)
        )
    ).mappings().one_or_none()
    if has_published is not None:
        version_id = has_published["id"]

    return WorkspaceOverview(
        system=system,
        rules=rules,
        books=books,
        rules_draft_present=draft is not None,
        rules_published=has_published is not None,
        books_published=books_published,
        published_rules_version_id=version_id,
    )
