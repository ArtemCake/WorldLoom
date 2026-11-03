# backend/app/modules/characters/api/runtime_api.py

"""HTTP-маршруты прежних боевых полей и активности игрового листа."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.infrastructure.database.session import get_async_session
from backend.app.modules.auth.dependencies import get_current_user
from backend.app.modules.characters.http import character_operation
from backend.app.modules.characters.schemas.sheet_runtime import (LegacySheetRead, LegacySheetUpdate, SheetActivityRead, SheetActivityUpdate,
                                                                  SpellSlotsUpdate)
from backend.app.modules.characters.services import sheet_runtime_service
from backend.app.modules.users.models.user import User
from backend.app.web.csrf import enforce_csrf

SessionDependency = Annotated[AsyncSession, Depends(get_async_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]

router = APIRouter(prefix="/sheets", tags=["characters"])
WRITE_DEPENDENCIES = [Depends(enforce_csrf)]

async def _get_actor_id(current_user: CurrentUser) -> UUID:
	return current_user.id

ActorId = Annotated[UUID, Depends(_get_actor_id)]

@router.get("/{sheet_id}/legacy", response_model=LegacySheetRead, operation_id="getLegacyCharacterSheet")
async def get_legacy_sheet(sheet_id: UUID, response: Response, actor_id: ActorId, session: SessionDependency) -> LegacySheetRead:
	response.headers["Cache-Control"] = "no-store"

	async with character_operation(session):
		return await sheet_runtime_service.get_legacy_sheet(session, sheet_id, actor_id)

@router.patch("/{sheet_id}", response_model=LegacySheetRead, operation_id="updateCharacterSheet", dependencies=WRITE_DEPENDENCIES)
async def update_character_sheet(sheet_id: UUID, data: LegacySheetUpdate, response: Response, actor_id: ActorId,
                                 session: SessionDependency) -> LegacySheetRead:
	response.headers["Cache-Control"] = "no-store"

	async with character_operation(session, write=True):
		return await sheet_runtime_service.update_legacy_sheet(session, sheet_id, actor_id, data)

@router.patch("/{sheet_id}/spell-slots", response_model=LegacySheetRead, operation_id="updateSpellSlots", dependencies=WRITE_DEPENDENCIES)
async def update_spell_slots(sheet_id: UUID, data: SpellSlotsUpdate, response: Response, actor_id: ActorId,
                             session: SessionDependency) -> LegacySheetRead:
	response.headers["Cache-Control"] = "no-store"

	async with character_operation(session, write=True):
		return await sheet_runtime_service.update_spell_slots(session, sheet_id, actor_id, data)

@router.patch("/{sheet_id}/activity", response_model=SheetActivityRead, operation_id="updateCharacterSheetActivity", dependencies=WRITE_DEPENDENCIES)
async def update_sheet_activity(sheet_id: UUID, data: SheetActivityUpdate, response: Response, actor_id: ActorId,
                                session: SessionDependency) -> SheetActivityRead:
	response.headers["Cache-Control"] = "no-store"

	async with character_operation(session, write=True):
		return await sheet_runtime_service.update_sheet_activity(session, sheet_id, actor_id, data)