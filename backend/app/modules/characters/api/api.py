# backend/app/modules/characters/api/api.py

"""HTTP-маршруты собственных персонажей и их игровых листов."""

from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.infrastructure.database.session import get_async_session
from backend.app.modules.auth.dependencies import get_current_user
from backend.app.modules.characters.services import service
from backend.app.modules.characters.http import character_operation
from backend.app.modules.characters.schemas.schemas import (CharacterCreate, CharacterDelete, CharacterListQuery, CharacterListRead, CharacterMetadataUpdate,
                                                    CharacterRead, CharacterSheetCreate, CharacterSheetRead, CharacterStateRead, CharacterStateUpdate, CharacterSummary)
from backend.app.modules.users.models.user import User
from backend.app.web.csrf import enforce_csrf
from backend.app.modules.characters.api.content_api import router as content_router
from backend.app.modules.characters.api.runtime_api import router as runtime_router



SessionDependency = Annotated[AsyncSession, Depends(get_async_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]

router = APIRouter(prefix="/characters", tags=["characters"])
WRITE_DEPENDENCIES = [Depends(enforce_csrf)]

async def _get_actor_id(current_user: CurrentUser) -> UUID:
	"""Получить идентификатор до завершения транзакции обработчика."""
	return current_user.id

ActorId = Annotated[UUID, Depends(_get_actor_id)]

@router.get("", response_model=CharacterListRead, operation_id="listCharacters")
async def list_characters(response: Response, actor_id: ActorId, session: SessionDependency,
                          limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0)) -> CharacterListRead:
	response.headers["Cache-Control"] = "no-store"
	query = CharacterListQuery(limit=limit, offset=offset)

	async with character_operation(session):
		return await service.list_characters(session, actor_id, query)

@router.post("", response_model=CharacterRead, status_code=201, operation_id="createCharacter", dependencies=WRITE_DEPENDENCIES)
async def create_character(data: CharacterCreate, response: Response, actor_id: ActorId, session: SessionDependency) -> CharacterRead:
	response.headers["Cache-Control"] = "no-store"

	async with character_operation(session, write=True):
		return await service.create_character(session, actor_id, data)

@router.get("/sheets/{sheet_id}", response_model=CharacterSheetRead, operation_id="getCharacterSheet")
async def get_character_sheet(sheet_id: UUID, response: Response, actor_id: ActorId, session: SessionDependency) -> CharacterSheetRead:
	response.headers["Cache-Control"] = "no-store"

	async with character_operation(session):
		return await service.get_character_sheet(session, sheet_id, actor_id)

@router.get("/sheets/{sheet_id}/state", response_model=CharacterStateRead, operation_id="getCharacterSheetState")
async def get_character_sheet_state(sheet_id: UUID, response: Response, actor_id: ActorId, session: SessionDependency) -> CharacterStateRead:
	response.headers["Cache-Control"] = "no-store"

	async with character_operation(session):
		return await service.get_character_sheet_state(session, sheet_id, actor_id)

@router.patch("/sheets/{sheet_id}/state", response_model=CharacterStateRead, operation_id="updateCharacterSheetState", dependencies=WRITE_DEPENDENCIES)
async def update_character_sheet_state(sheet_id: UUID, data: CharacterStateUpdate, response: Response, actor_id: ActorId,
                                       session: SessionDependency) -> CharacterStateRead:
	response.headers["Cache-Control"] = "no-store"

	async with character_operation(session, write=True):
		return await service.update_character_sheet_state(session, sheet_id, actor_id, data)

@router.get("/{character_id}", response_model=CharacterRead, operation_id="getCharacter")
async def get_character(character_id: UUID, response: Response, actor_id: ActorId, session: SessionDependency) -> CharacterRead:
	response.headers["Cache-Control"] = "no-store"

	async with character_operation(session):
		return await service.get_character(session, character_id, actor_id)

@router.patch("/{character_id}/metadata", response_model=CharacterSummary, operation_id="updateCharacterMetadata", dependencies=WRITE_DEPENDENCIES)
async def update_character_metadata(character_id: UUID, data: CharacterMetadataUpdate, response: Response, actor_id: ActorId,
                                    session: SessionDependency) -> CharacterSummary:
	response.headers["Cache-Control"] = "no-store"

	async with character_operation(session, write=True):
		return await service.update_character_metadata(session, character_id, actor_id, data)

@router.delete("/{character_id}", status_code=204, operation_id="deleteCharacter", dependencies=WRITE_DEPENDENCIES)
async def delete_character(character_id: UUID, data: CharacterDelete, actor_id: ActorId, session: SessionDependency) -> Response:
	async with character_operation(session, write=True):
		await service.delete_character(session, character_id, actor_id, data)

	return Response(status_code=204, headers={"Cache-Control": "no-store"})

@router.get("/{character_id}/state", response_model=CharacterStateRead, operation_id="getCharacterState")
async def get_character_state(character_id: UUID, response: Response, actor_id: ActorId, session: SessionDependency) -> CharacterStateRead:
	response.headers["Cache-Control"] = "no-store"

	async with character_operation(session):
		return await service.get_character_state(session, character_id, actor_id)

@router.patch("/{character_id}/state", response_model=CharacterStateRead, operation_id="updateCharacterState", dependencies=WRITE_DEPENDENCIES)
async def update_character_state(character_id: UUID, data: CharacterStateUpdate, response: Response, actor_id: ActorId,
                                 session: SessionDependency) -> CharacterStateRead:
	response.headers["Cache-Control"] = "no-store"

	async with character_operation(session, write=True):
		return await service.update_character_state(session, character_id, actor_id, data)

@router.post("/{character_id}/sheets", response_model=CharacterSheetRead, status_code=201, operation_id="createCharacterSheet",
             dependencies=WRITE_DEPENDENCIES)
async def create_character_sheet(character_id: UUID, data: CharacterSheetCreate, response: Response, actor_id: ActorId,
                                 session: SessionDependency) -> CharacterSheetRead:
	response.headers["Cache-Control"] = "no-store"

	async with character_operation(session, write=True):
		if data.character_id != character_id:
			raise HTTPException(
				status_code=422,
				detail="Идентификатор персонажа в адресе и теле запроса должен совпадать.",
				headers={"Cache-Control": "no-store"},
			)

		return await service.create_character_sheet(session, actor_id, data)

router.include_router(content_router)
router.include_router(runtime_router)