# backend/app/modules/admin/catalog_api.py

"""Административное управление карточками игровых систем без изменения их правил."""

from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.infrastructure.database.session import get_async_session
from backend.app.modules.admin.dependencies import require_content_manager
from backend.app.modules.catalog import service
from backend.app.modules.catalog.http import catalog_operation
from backend.app.modules.catalog.schemas import GameSystemAdminRead, GameSystemCreate, GameSystemUpdate
from backend.app.web.csrf import enforce_csrf


SessionDependency = Annotated[AsyncSession, Depends(get_async_session)]

router = APIRouter(prefix="/admin/game-systems", tags=["admin"], dependencies=[Depends(require_content_manager)])

@router.get("/list", response_model=list[GameSystemAdminRead], operation_id="adminListGameSystems")
async def list_game_systems(response: Response, session: SessionDependency) -> list[GameSystemAdminRead]:
	response.headers["Cache-Control"] = "no-store"

	async with catalog_operation(session):
		systems = await service.list_all_systems(session)
		return [GameSystemAdminRead.model_validate(system) for system in systems]

@router.get("/{system_id}", response_model=GameSystemAdminRead, operation_id="adminGetGameSystem")
async def get_game_system(system_id: UUID, response: Response, session: SessionDependency) -> GameSystemAdminRead:
	response.headers["Cache-Control"] = "no-store"

	async with catalog_operation(session):
		system = await service.get_game_system(session, system_id)
		return GameSystemAdminRead.model_validate(system)

@router.post("", response_model=GameSystemAdminRead, status_code=201, operation_id="adminCreateGameSystem", dependencies=[Depends(enforce_csrf)])
async def create_game_system(data: GameSystemCreate, response: Response, session: SessionDependency) -> GameSystemAdminRead:
	response.headers["Cache-Control"] = "no-store"

	async with catalog_operation(session, write=True):
		system = await service.create_game_system(session, data)
		return GameSystemAdminRead.model_validate(system)

@router.patch("/{system_id}", response_model=GameSystemAdminRead, operation_id="adminUpdateGameSystem", dependencies=[Depends(enforce_csrf)])
async def update_game_system(system_id: UUID, data: GameSystemUpdate, response: Response, session: SessionDependency) -> GameSystemAdminRead:
	response.headers["Cache-Control"] = "no-store"

	async with catalog_operation(session, write=True):
		system = await service.update_game_system(session, system_id, data)
		return GameSystemAdminRead.model_validate(system)