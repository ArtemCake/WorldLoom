# backend/app/modules/games/routers/lobby.py

"""HTTP API лобби с общей границей транзакций модуля игр."""

from __future__ import annotations
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.modules.games import errors
from backend.app.modules.games.dependencies import ActorId, OperationSession, WRITE_DEPENDENCIES, get_resources, write_operation
from backend.app.modules.games.schemas.lobby import GameCreate, GameRead, GameUpdate, InviteClaim, InviteCreate, InviteRead
from backend.app.modules.games.schemas.lobby import PartyRead, PartyRoleUpdate, SessionCreate, SessionRead, SessionUpdate
from backend.app.modules.games.services import game_deletion_service
from backend.app.modules.games.services import lobby_service as service
from backend.app.web.exception_handlers import GameErrorRoute
from backend.app.core.map_storage import get_map_images_root


router = APIRouter(prefix="/games", tags=["lobby"], route_class=GameErrorRoute)

def _image_root(request: Request) -> Path:
	"""Использовать общий корень при подготовке удаления игры."""
	return get_map_images_root(get_resources(request).settings)

def _session_read(value: Any, game_id: UUID) -> SessionRead:
	if value.game_id != game_id:
		raise errors.GameSessionNotFound("Сессия этой игры не найдена")

	return SessionRead.model_validate(value)

async def _stage_deletion(session: AsyncSession, game_id: UUID, actor_id: UUID, root: Path) -> dict[str, Any]:
	await game_deletion_service.stage_game_deletion(session, game_id, actor_id, root=root)

	try:
		job = await game_deletion_service.get_cleanup_job(session, game_id, actor_id, root=root)
	except errors.GameCleanupJobNotFound:
		raise errors.GameNotFound("Игра и сохранённое задание её удаления не найдены") from None

	return {"game_id": str(game_id), "deleted": True, "cleanup_complete": job["cleanup_complete"]}

ImageRoot = Annotated[Path, Depends(_image_root)]

@router.get("/list", response_model=list[GameRead], operation_id="listGames")
async def list_games(actor_id: ActorId, session: OperationSession) -> list[GameRead]:
	return [GameRead.model_validate(game) for game in await service.list_games_for_user(session, actor_id)]

@router.post("", response_model=GameRead, status_code=201, operation_id="createGame", dependencies=WRITE_DEPENDENCIES)
async def create_game(data: GameCreate, actor_id: ActorId, session: OperationSession) -> GameRead:
	return await write_operation(session, service.create_game(session, actor_id, data), GameRead.model_validate)

@router.post("/invites/claim", response_model=PartyRead, operation_id="claimInvite", dependencies=WRITE_DEPENDENCIES)
async def claim_invite(data: InviteClaim, actor_id: ActorId, session: OperationSession) -> PartyRead:
	return await write_operation(session, service.claim_invite(session, data.token, actor_id), PartyRead.model_validate)

@router.get("/{game_id}", response_model=GameRead, operation_id="getGame")
async def get_game(game_id: UUID, actor_id: ActorId, session: OperationSession) -> GameRead:
	return GameRead.model_validate(await service.get_game(session, game_id, actor_id))

@router.patch("/{game_id}", response_model=GameRead, operation_id="updateGame", dependencies=WRITE_DEPENDENCIES)
async def update_game(game_id: UUID, data: GameUpdate, actor_id: ActorId, session: OperationSession) -> GameRead:
	return await write_operation(session, service.update_game(session, game_id, actor_id, data), GameRead.model_validate)

@router.delete("/{game_id}", status_code=204, operation_id="archiveGame", dependencies=WRITE_DEPENDENCIES)
async def archive_game(game_id: UUID, actor_id: ActorId, session: OperationSession) -> Response:
	await write_operation(session, service.archive_game(session, game_id, actor_id))
	return Response(status_code=204)

@router.get("/{game_id}/party", response_model=list[PartyRead], operation_id="listParty")
async def list_party(game_id: UUID, actor_id: ActorId, session: OperationSession) -> list[PartyRead]:
	return [PartyRead.model_validate(member) for member in await service.list_party(session, game_id, actor_id)]

@router.patch("/{game_id}/party/{user_id}", response_model=PartyRead, operation_id="updatePartyRole", dependencies=WRITE_DEPENDENCIES)
async def update_party_role(game_id: UUID, user_id: UUID, data: PartyRoleUpdate, actor_id: ActorId, session: OperationSession) -> PartyRead:
	operation = service.update_party_role(session, game_id, user_id, actor_id, data.role_in_game)
	return await write_operation(session, operation, PartyRead.model_validate)

@router.post("/{game_id}/leave", status_code=204, operation_id="leaveGame", dependencies=WRITE_DEPENDENCIES)
async def leave_game(game_id: UUID, actor_id: ActorId, session: OperationSession) -> Response:
	await write_operation(session, service.leave_game(session, game_id, actor_id))
	return Response(status_code=204)

@router.post("/{game_id}/invites", response_model=InviteRead, status_code=201, operation_id="createInvite", dependencies=WRITE_DEPENDENCIES)
async def create_invite(game_id: UUID, data: InviteCreate, actor_id: ActorId, session: OperationSession) -> InviteRead:
	return await write_operation(session, service.create_invite(session, game_id, actor_id, data), InviteRead.model_validate)

@router.post("/{game_id}/sessions", response_model=SessionRead, status_code=201, operation_id="startSession", dependencies=WRITE_DEPENDENCIES)
async def start_session(game_id: UUID, data: SessionCreate, actor_id: ActorId, session: OperationSession) -> SessionRead:
	return await write_operation(session, service.start_session(session, game_id, actor_id, data), SessionRead.model_validate)

@router.get("/{game_id}/sessions", response_model=list[SessionRead], operation_id="listSessions")
async def list_sessions(game_id: UUID, actor_id: ActorId, session: OperationSession) -> list[SessionRead]:
	return [SessionRead.model_validate(meeting) for meeting in await service.list_sessions(session, game_id, actor_id)]

@router.get("/{game_id}/sessions/active", response_model=SessionRead, operation_id="getActiveSession")
async def get_active_session(game_id: UUID, actor_id: ActorId, session: OperationSession) -> SessionRead:
	return SessionRead.model_validate(await service.get_active_session(session, game_id, actor_id))

@router.patch("/{game_id}/sessions/{session_id}", response_model=SessionRead, operation_id="updateSession", dependencies=WRITE_DEPENDENCIES)
async def update_session(game_id: UUID, session_id: UUID, data: SessionUpdate, actor_id: ActorId, session: OperationSession) -> SessionRead:
	operation = service.update_session(session, session_id, actor_id, data)
	return await write_operation(session, operation, lambda value: _session_read(value, game_id))

@router.post("/{game_id}/sessions/{session_id}/end", response_model=SessionRead, operation_id="endSession", dependencies=WRITE_DEPENDENCIES)
async def end_session(game_id: UUID, session_id: UUID, actor_id: ActorId, session: OperationSession) -> SessionRead:
	operation = service.end_session(session, session_id, actor_id)
	return await write_operation(session, operation, lambda value: _session_read(value, game_id))

@router.delete("/{game_id}/permanent", name="delete_game_permanently", operation_id="deleteGamePermanently",
	dependencies=WRITE_DEPENDENCIES, responses={202: {"description": "Удаление сохранено; очистка файлов ожидается"}})
async def delete_game_permanently(game_id: UUID, actor_id: ActorId, session: OperationSession, root: ImageRoot) -> JSONResponse:
	result = await write_operation(session, _stage_deletion(session, game_id, actor_id, root))
	return JSONResponse(
		status_code=200 if result["cleanup_complete"] else 202,
		content=result,
		headers={"Cache-Control": "no-store"},
	)