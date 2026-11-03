# backend/app/modules/games/pages.py

"""HTML-страницы списка игр, подробностей и игрового стола."""

from __future__ import annotations
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Request
from fastapi_csrf_protect import CsrfProtect
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import HTMLResponse
from backend.app.infrastructure.database.session import get_async_session
from backend.app.modules.auth.dependencies import get_current_user
from backend.app.modules.games.errors import GameSessionNotFound
from backend.app.modules.games.services import lobby_service as service
from backend.app.modules.users.models.user import User
from backend.app.web.exception_handlers import GameErrorRoute
from backend.app.web.rendering import render_page
from backend.app.modules.maps.services import map_management_service as map_management


router = APIRouter(prefix="/games", tags=["game-pages"], route_class=GameErrorRoute)

PageUser = Annotated[User, Depends(get_current_user)]
PageSession = Annotated[AsyncSession, Depends(get_async_session)]
PageCsrf = Annotated[CsrfProtect, Depends()]

@router.get("", response_class=HTMLResponse, name="games_page_get", operation_id="getGamesPage")
async def get_games_page(request: Request, user: PageUser, csrf_protect: PageCsrf) -> HTMLResponse:
	return render_page(request, "games/games.html", {"user": user}, csrf_protect)

@router.get("/{game_id}/details", response_class=HTMLResponse, name="game_details_page_get", operation_id="getGameDetailsPage")
async def get_game_details_page(request: Request, game_id: UUID, user: PageUser, session: PageSession, csrf_protect: PageCsrf) -> HTMLResponse:
	game = await service.get_game(session, game_id, user.id)

	context = {"user": user, "game": game, "is_game_master": game.master_id == user.id}
	return render_page(request, "games/game_details.html", context, csrf_protect)

@router.get("/{game_id}/play", response_class=HTMLResponse, name="game_play_page_get", operation_id="getGamePlayPage")
async def get_game_play_page(request: Request, game_id: UUID, user: PageUser, session: PageSession, csrf_protect: PageCsrf,
    session_id: UUID | None = None) -> HTMLResponse:
	game = await service.get_game(session, game_id, user.id)
	game_sessions = await service.list_sessions(session, game_id, user.id)
	active_session = next((item for item in game_sessions if item.is_active), None)

	if session_id is not None:
		selected_session = next((item for item in game_sessions if item.id == session_id), None)

		if selected_session is None:
			raise GameSessionNotFound("Сессия этой игры не найдена")
	else:
		selected_session = active_session
	can_manage_tokens = bool(selected_session and selected_session.is_active and game.master_id == user.id and game.status != "archived")
	token_maps = []

	if can_manage_tokens:
		campaign_maps = await map_management.list_maps_for_game(session, game_id, user.id)
		token_maps = [
			{"id": str(campaign_map.id), "title": campaign_map.title}
			for campaign_map in campaign_maps
			if campaign_map.session_id is None or campaign_map.session_id == selected_session.id
		]

	context = {
		"user": user,
		"game": game,
		"game_id": game_id,
		"game_sessions": game_sessions,
		"selected_session": selected_session,
		"session_id": selected_session.id if selected_session else None,
		"active_session": active_session,
		"is_game_master": game.master_id == user.id,
		"can_manage_tokens": can_manage_tokens,
		"token_maps": token_maps,
		"can_view_master_map": game.master_id == user.id,
		"can_manage_combat": bool(selected_session and game.master_id == user.id),
	}
	return render_page(request, "games/game_play.html", context, csrf_protect)