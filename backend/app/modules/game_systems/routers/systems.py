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