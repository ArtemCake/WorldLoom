# backend/app/modules/catalog/api.py

"""Чтение активных карточек систем и возможностей административного интерфейса."""

from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.infrastructure.database.session import get_async_session
from backend.app.modules.auth.dependencies import get_current_user
from backend.app.modules.catalog import service
from backend.app.modules.catalog.http import catalog_operation
from backend.app.modules.catalog.schemas import GameSystemRead, GameSystemsCatalogAccess
from backend.app.modules.users.enums import AdminPermission
from backend.app.modules.users.models.user import User
from backend.app.modules.users.permissions import has_admin_permission


SessionDependency = Annotated[AsyncSession, Depends(get_async_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]

router = APIRouter(prefix="/game-systems", tags=["content"], dependencies=[Depends(get_current_user)])

@router.get("", response_model=list[GameSystemRead], operation_id="listGameSystems")
async def list_game_systems(response: Response, session: SessionDependency) -> list[GameSystemRead]:
	response.headers["Cache-Control"] = "no-store"

	async with catalog_operation(session):
		systems = await service.list_active_systems(session)
		return [GameSystemRead.model_validate(system) for system in systems]

@router.get("/access", response_model=GameSystemsCatalogAccess, operation_id="getGameSystemsCatalogAccess")
async def game_systems_catalog_access(response: Response, current_user: CurrentUser) -> GameSystemsCatalogAccess:
	response.headers["Cache-Control"] = "no-store"
	can_manage = has_admin_permission(current_user.roles, current_user.admin_permissions, AdminPermission.CONTENT)

	return GameSystemsCatalogAccess(
		can_create=can_manage,
		can_edit=can_manage,
		can_toggle=can_manage,
		can_delete=can_manage,
		list_url="/admin/game-systems/list" if can_manage else "/game-systems",
	)

@router.get("/items/{system_id}", response_model=GameSystemRead, operation_id="getActiveGameSystem")
async def get_active_game_system(system_id: UUID, response: Response, session: SessionDependency) -> GameSystemRead:
	response.headers["Cache-Control"] = "no-store"

	async with catalog_operation(session):
		system = await service.get_game_system(session, system_id, active_only=True)
		return GameSystemRead.model_validate(system)