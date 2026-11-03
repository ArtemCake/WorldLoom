# backend/app/modules/characters/api/content_api.py

"""HTTP-маршруты заклинаний и инвентаря собственных игровых листов."""

from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.infrastructure.database.session import get_async_session
from backend.app.modules.auth.dependencies import get_current_user
from backend.app.modules.characters.services import content_service
from backend.app.modules.characters.schemas.content_schemas import (InventoryItemIn, InventoryItemRead, InventoryItemUpdate, SpellOnSheetIn,
                                                            SpellOnSheetRead, SpellOnSheetUpdate)
from backend.app.modules.characters.http import character_operation
from backend.app.modules.users.models.user import User
from backend.app.web.csrf import enforce_csrf


SessionDependency = Annotated[AsyncSession, Depends(get_async_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]

router = APIRouter(prefix="/sheets", tags=["characters"])
WRITE_DEPENDENCIES = [Depends(enforce_csrf)]

async def _get_actor_id(current_user: CurrentUser) -> UUID:
	return current_user.id

ActorId = Annotated[UUID, Depends(_get_actor_id)]

@router.get("/{sheet_id}/spells", response_model=list[SpellOnSheetRead], operation_id="listCharacterSheetSpells")
async def list_sheet_spells(sheet_id: UUID, response: Response, actor_id: ActorId, session: SessionDependency) -> list[SpellOnSheetRead]:
	response.headers["Cache-Control"] = "no-store"

	async with character_operation(session):
		return await content_service.list_sheet_spells(session, sheet_id, actor_id)

@router.post("/{sheet_id}/spells", response_model=SpellOnSheetRead, status_code=201, operation_id="addSpellToSheet",
             dependencies=WRITE_DEPENDENCIES)
async def add_spell_to_sheet(sheet_id: UUID, data: SpellOnSheetIn, response: Response, actor_id: ActorId,
                             session: SessionDependency) -> SpellOnSheetRead:
	response.headers["Cache-Control"] = "no-store"

	async with character_operation(session, write=True):
		return await content_service.add_spell_to_sheet(session, sheet_id, actor_id, data)

@router.patch("/{sheet_id}/spells/{spell_link_id}", response_model=SpellOnSheetRead, operation_id="updateSheetSpell",
              dependencies=WRITE_DEPENDENCIES)
async def update_sheet_spell(sheet_id: UUID, spell_link_id: UUID, data: SpellOnSheetUpdate, response: Response, actor_id: ActorId,
                             session: SessionDependency) -> SpellOnSheetRead:
	response.headers["Cache-Control"] = "no-store"

	async with character_operation(session, write=True):
		return await content_service.update_sheet_spell(session, sheet_id, spell_link_id, actor_id, data)

@router.delete("/{sheet_id}/spells/{spell_link_id}", status_code=204, operation_id="removeSpellFromSheet", dependencies=WRITE_DEPENDENCIES)
async def remove_spell_from_sheet(sheet_id: UUID, spell_link_id: UUID, actor_id: ActorId, session: SessionDependency) -> Response:
	async with character_operation(session, write=True):
		await content_service.remove_spell_from_sheet(session, sheet_id, spell_link_id, actor_id)

	return Response(status_code=204, headers={"Cache-Control": "no-store"})

@router.get("/{sheet_id}/inventory", response_model=list[InventoryItemRead], operation_id="listCharacterSheetInventory")
async def list_sheet_inventory(sheet_id: UUID, response: Response, actor_id: ActorId, session: SessionDependency) -> list[InventoryItemRead]:
	response.headers["Cache-Control"] = "no-store"

	async with character_operation(session):
		return await content_service.list_sheet_inventory(session, sheet_id, actor_id)

@router.post("/{sheet_id}/inventory", response_model=InventoryItemRead, status_code=201, operation_id="addItemToInventory",
             dependencies=WRITE_DEPENDENCIES)
async def add_item_to_inventory(sheet_id: UUID, data: InventoryItemIn, response: Response, actor_id: ActorId,
                                session: SessionDependency) -> InventoryItemRead:
	response.headers["Cache-Control"] = "no-store"

	async with character_operation(session, write=True):
		return await content_service.add_item_to_inventory(session, sheet_id, actor_id, data)

@router.patch("/{sheet_id}/inventory/{item_id}", response_model=InventoryItemRead, operation_id="updateInventoryItem",
              dependencies=WRITE_DEPENDENCIES)
async def update_inventory_item(sheet_id: UUID, item_id: UUID, data: InventoryItemUpdate, response: Response, actor_id: ActorId,
                                session: SessionDependency) -> InventoryItemRead:
	response.headers["Cache-Control"] = "no-store"

	async with character_operation(session, write=True):
		return await content_service.update_inventory_item(session, sheet_id, item_id, actor_id, data)

@router.delete("/{sheet_id}/inventory/{item_id}", status_code=204, operation_id="removeItemFromInventory", dependencies=WRITE_DEPENDENCIES)
async def remove_item_from_inventory(sheet_id: UUID, item_id: UUID, actor_id: ActorId, session: SessionDependency) -> Response:
	async with character_operation(session, write=True):
		await content_service.remove_item_from_inventory(session, sheet_id, item_id, actor_id)

	return Response(status_code=204, headers={"Cache-Control": "no-store"})