# backend/app/modules/games/routers/game_state.py

"""HTTP-маршруты токенов, ручной очереди и бросков игрового стола."""

from __future__ import annotations
from collections.abc import Awaitable
from typing import Annotated, Any
from uuid import UUID
from fastapi import APIRouter, Body, Query, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import JsonValue
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.modules.games.dependencies import ActorId, OperationSession, WRITE_DEPENDENCIES, write_operation
from backend.app.modules.games.schemas.dice import DiceRollIn, DiceRollRead
from backend.app.modules.games.schemas.game_state import TokenCreate, TokenMove, TokenRead, TokenUpdate
from backend.app.modules.games.services import dice_service, initiative_service, token_service
from backend.app.web.exception_handlers import GameErrorRoute


router = APIRouter(prefix="/sessions", tags=["game_state"], route_class=GameErrorRoute)
Combatants = Annotated[list[dict[str, JsonValue]], Body(min_length=1, max_length=1000)]

async def _token_result(session: AsyncSession, operation: Awaitable[Any]) -> TokenRead:
	token = await operation
	await session.refresh(token, attribute_names=["created_at", "updated_at"])
	return TokenRead.model_validate(token)

async def _roll_result(session: AsyncSession, operation: Awaitable[Any]) -> DiceRollRead:
	dice_roll = await operation
	await session.refresh(dice_roll, attribute_names=["created_at"])
	return DiceRollRead.model_validate(dice_roll)

def _tracker_response(tracker: Any) -> JSONResponse:
	content = {
		"session_id": tracker.session_id,
		"turn_order": tracker.turn_order_json,
		"current_index": tracker.current_index,
		"round_number": tracker.round_number,
	}
	return JSONResponse(content=jsonable_encoder(content), headers={"Cache-Control": "no-store"})

@router.post("/tokens", response_model=TokenRead, status_code=201, operation_id="createToken", dependencies=WRITE_DEPENDENCIES)
async def create_token(data: TokenCreate, actor_id: ActorId, session: OperationSession) -> TokenRead:
	operation = token_service.create_token(session, actor_id, data)
	return await write_operation(session, _token_result(session, operation))

@router.get("/{session_id}/tokens", response_model=list[TokenRead], operation_id="listTokens")
async def list_tokens(session_id: UUID, actor_id: ActorId, session: OperationSession) -> list[TokenRead]:
	tokens = await token_service.list_tokens_for_session(session, session_id, actor_id)
	return [TokenRead.model_validate(token) for token in tokens]

@router.patch("/tokens/{token_id}", response_model=TokenRead, operation_id="updateToken", dependencies=WRITE_DEPENDENCIES)
async def update_token(token_id: UUID, data: TokenUpdate, actor_id: ActorId, session: OperationSession) -> TokenRead:
	operation = token_service.update_token(session, token_id, actor_id, data)
	return await write_operation(session, _token_result(session, operation))

@router.post("/tokens/{token_id}/move", response_model=TokenRead, operation_id="moveToken", dependencies=WRITE_DEPENDENCIES)
async def move_token(token_id: UUID, data: TokenMove, actor_id: ActorId, session: OperationSession) -> TokenRead:
	operation = token_service.move_token(session, token_id, actor_id, data)
	return await write_operation(session, _token_result(session, operation))

@router.delete("/tokens/{token_id}", status_code=204, operation_id="deleteToken", dependencies=WRITE_DEPENDENCIES)
async def delete_token(token_id: UUID, actor_id: ActorId, session: OperationSession) -> Response:
	await write_operation(session, token_service.delete_token(session, token_id, actor_id))
	return Response(status_code=204)

@router.get("/{session_id}/combat", operation_id="getCombatState")
async def get_combat_state(session_id: UUID, actor_id: ActorId, session: OperationSession) -> JSONResponse:
	content = await initiative_service.get_combat_state(session, session_id, actor_id)
	return JSONResponse(content=jsonable_encoder(content), headers={"Cache-Control": "no-store"})

@router.post("/{session_id}/combat/start", operation_id="startCombat", dependencies=WRITE_DEPENDENCIES)
async def start_combat(session_id: UUID, combatants: Combatants, actor_id: ActorId, session: OperationSession) -> JSONResponse:
	operation = initiative_service.start_combat(session, session_id, actor_id, combatants)
	return await write_operation(session, operation, _tracker_response)

@router.post("/{session_id}/combat/next-turn", operation_id="nextTurn", dependencies=WRITE_DEPENDENCIES)
async def next_turn(session_id: UUID, actor_id: ActorId, session: OperationSession) -> JSONResponse:
	operation = initiative_service.next_turn(session, session_id, actor_id)
	return await write_operation(session, operation, _tracker_response)

@router.post("/{session_id}/combat/end", status_code=204, operation_id="endCombat", dependencies=WRITE_DEPENDENCIES)
async def end_combat(session_id: UUID, actor_id: ActorId, session: OperationSession) -> Response:
	await write_operation(session, initiative_service.end_combat(session, session_id, actor_id))
	return Response(status_code=204)

@router.post("/{session_id}/roll", response_model=DiceRollRead, status_code=201, operation_id="rollDice", dependencies=WRITE_DEPENDENCIES)
async def roll_dice(session_id: UUID, data: DiceRollIn, actor_id: ActorId, session: OperationSession, party_id: UUID | None = None) -> DiceRollRead:
	operation = dice_service.roll_dice(session, session_id, actor_id, party_id, data)
	return await write_operation(session, _roll_result(session, operation))

@router.get("/{session_id}/rolls", response_model=list[DiceRollRead], operation_id="listRolls")
async def list_rolls(session_id: UUID, actor_id: ActorId, session: OperationSession, limit: int = Query(default=100, ge=1, le=500),
		offset: int = Query(default=0, ge=0, le=1_000_000)) -> list[DiceRollRead]:
	rolls = await dice_service.list_session_rolls(session, session_id, actor_id, limit=limit, offset=offset)
	return [DiceRollRead.model_validate(item) for item in rolls]