# backend/app/modules/game_systems/routers/systems.py

"""Чтение опубликованных правил активных игровых систем."""

from __future__ import annotations
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID
from fastapi import (APIRouter, Depends, HTTPException, Response)
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.infrastructure.database.session import (get_async_session)
from backend.app.modules.auth.dependencies import (get_current_user)
from backend.app.modules.game_systems.errors import (GameSystemError, GameSystemNotFound, GameSystemRulesStorageError)
from backend.app.modules.game_systems.schemas.game_rules import (GameSystemRulesPublishedState, GameSystemRulesVersionRead)
from backend.app.modules.game_systems.services import (editor_service)
from backend.app.modules.game_systems.schemas.game_rules import GameSystemRulesVersionPage
from backend.app.modules.game_systems.schemas.game_system_versions import (
	GameSystemTextPublishedState, GameSystemTextVersionPage, GameSystemTextVersionRead,
	GameSystemMechanicPublishedState, GameSystemMechanicVersionPage, GameSystemMechanicVersionRead,
	GameSystemVersionPage, GameSystemCurrentVersionState, GameSystemVersionRead,
	GameSystemPublishedDocumentState,
)
from backend.app.modules.game_systems.services import text_service, mechanic_service, version_service


logger = logging.getLogger(__name__)

SessionDependency = Annotated[
	AsyncSession,
	Depends(get_async_session),
]

router = APIRouter(
	prefix="/game-systems",
	tags=["game-systems"],
	dependencies=[Depends(get_current_user)],
)

@asynccontextmanager
async def _read_operation(session: AsyncSession) -> AsyncIterator[None]:
	"""Освободить транзакцию чтения до возврата схемы ответа."""
	try:
		yield

	except GameSystemNotFound as exc:
		raise HTTPException(
			status_code=404,
			detail="Система или публикация не найдена",
		) from exc

	except GameSystemRulesStorageError as exc:
		logger.exception(
			"Неподдерживаемые сохранённые правила"
		)
		raise HTTPException(
			status_code=500,
			detail="Не удалось прочитать сохранённые правила",
		) from exc

	except GameSystemError as exc:
		logger.exception(
			"Ошибка чтения правил игровой системы"
		)
		raise HTTPException(
			status_code=500,
			detail="Не удалось получить правила",
		) from exc

	finally:
		await session.rollback()

@router.get("/items/{system_id}/rules/latest", response_model=GameSystemRulesPublishedState, operation_id="getActiveGameSystemPublishedRules")
async def get_latest_rules(system_id: UUID, response: Response, session: SessionDependency) -> GameSystemRulesPublishedState:
	response.headers["Cache-Control"] = "no-store"

	async with _read_operation(session):
		version = await editor_service.get_latest_rules_version(
			session,
			system_id,
		)
		return GameSystemRulesPublishedState(version=version)

@router.get("/items/{system_id}/rules/versions", response_model=GameSystemRulesVersionPage)
async def get_rules_history(system_id: UUID, response: Response, session: SessionDependency, limit: int = 20, before: int | None = None):
	response.headers["Cache-Control"] = "no-store"

	async with _read_operation(session):
		return await editor_service.list_publications(session, system_id, limit=limit, before=before)

@router.get("/items/{system_id}/rules/versions/{version_id}", response_model=GameSystemRulesVersionRead, operation_id="getActiveGameSystemRulesVersion")
async def get_rules_version(system_id: UUID, version_id: UUID, response: Response, session: SessionDependency) -> GameSystemRulesVersionRead:
	response.headers["Cache-Control"] = "no-store"

	async with _read_operation(session):
		return await editor_service.get_rules_version(
			session,
			system_id,
			version_id,
		)


# ── Публичные read-маршруты для раздельных блоков ─────────────────────────────

@router.get("/items/{system_id}/text/latest", response_model=GameSystemTextPublishedState, operation_id="getActiveGameSystemLatestText")
async def get_latest_text(system_id: UUID, response: Response, session: SessionDependency) -> GameSystemTextPublishedState:
	response.headers["Cache-Control"] = "no-store"

	async with _read_operation(session):
		version = await text_service.get_latest_text_version(session, system_id)
		return GameSystemTextPublishedState(version=version)


@router.get("/items/{system_id}/text/versions", response_model=GameSystemTextVersionPage, operation_id="listActiveGameSystemTextVersions")
async def list_text_versions(system_id: UUID, response: Response, session: SessionDependency, limit: int = 20, before: int | None = None) -> GameSystemTextVersionPage:
	response.headers["Cache-Control"] = "no-store"

	async with _read_operation(session):
		return await text_service.list_text_versions(session, system_id, limit=limit, before=before)


@router.get("/items/{system_id}/text/versions/{version_id}", response_model=GameSystemTextVersionRead, operation_id="getActiveGameSystemTextVersion")
async def get_text_version(system_id: UUID, version_id: UUID, response: Response, session: SessionDependency) -> GameSystemTextVersionRead:
	response.headers["Cache-Control"] = "no-store"

	async with _read_operation(session):
		return await text_service.get_text_version(session, system_id, version_id)


@router.get("/items/{system_id}/mechanic/latest", response_model=GameSystemMechanicPublishedState, operation_id="getActiveGameSystemLatestMechanic")
async def get_latest_mechanic(system_id: UUID, response: Response, session: SessionDependency) -> GameSystemMechanicPublishedState:
	response.headers["Cache-Control"] = "no-store"

	async with _read_operation(session):
		version = await mechanic_service.get_latest_mechanic_version(session, system_id)
		return GameSystemMechanicPublishedState(version=version)


@router.get("/items/{system_id}/mechanic/versions", response_model=GameSystemMechanicVersionPage, operation_id="listActiveGameSystemMechanicVersions")
async def list_mechanic_versions(system_id: UUID, response: Response, session: SessionDependency, limit: int = 20, before: int | None = None) -> GameSystemMechanicVersionPage:
	response.headers["Cache-Control"] = "no-store"

	async with _read_operation(session):
		return await mechanic_service.list_mechanic_versions(session, system_id, limit=limit, before=before)


@router.get("/items/{system_id}/mechanic/versions/{version_id}", response_model=GameSystemMechanicVersionRead, operation_id="getActiveGameSystemMechanicVersion")
async def get_mechanic_version(system_id: UUID, version_id: UUID, response: Response, session: SessionDependency) -> GameSystemMechanicVersionRead:
	response.headers["Cache-Control"] = "no-store"

	async with _read_operation(session):
		return await mechanic_service.get_mechanic_version(session, system_id, version_id)


@router.get("/items/{system_id}/versions/current", response_model=GameSystemCurrentVersionState, operation_id="getCurrentGameSystemVersion")
async def get_current_version(system_id: UUID, response: Response, session: SessionDependency) -> GameSystemCurrentVersionState:
	response.headers["Cache-Control"] = "no-store"

	async with _read_operation(session):
		return await version_service.get_current_version_state(session, system_id)


@router.get("/items/{system_id}/versions", response_model=GameSystemVersionPage, operation_id="listActiveGameSystemVersions")
async def list_system_versions(system_id: UUID, response: Response, session: SessionDependency, limit: int = 20, before: int | None = None) -> GameSystemVersionPage:
	response.headers["Cache-Control"] = "no-store"

	async with _read_operation(session):
		return await version_service.list_system_versions(session, system_id, limit=limit, before=before)


@router.get("/items/{system_id}/versions/{version_id}", response_model=GameSystemVersionRead, operation_id="getActiveGameSystemVersion")
async def get_system_version(system_id: UUID, version_id: UUID, response: Response, session: SessionDependency) -> GameSystemVersionRead:
	response.headers["Cache-Control"] = "no-store"

	async with _read_operation(session):
		return await version_service.get_system_version(session, system_id, version_id)


@router.get("/items/{system_id}/published", response_model=GameSystemPublishedDocumentState, operation_id="getActiveGameSystemPublishedDocument")
async def get_published_document(system_id: UUID, response: Response, session: SessionDependency) -> GameSystemPublishedDocumentState:
	response.headers["Cache-Control"] = "no-store"

	async with _read_operation(session):
		return await version_service.get_published_document(session, system_id)


@router.get("/items/{system_id}/published/{version_id}", response_model=GameSystemPublishedDocumentState, operation_id="getActiveGameSystemPublishedVersionDocument")
async def get_published_version_document(system_id: UUID, version_id: UUID, response: Response, session: SessionDependency) -> GameSystemPublishedDocumentState:
	response.headers["Cache-Control"] = "no-store"

	async with _read_operation(session):
		return await version_service.get_published_document(session, system_id, version_id)