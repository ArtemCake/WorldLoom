# backend/app/modules/maps/pages.py

"""HTML-страницы каталога, создания, редактирования и просмотра карт."""

from __future__ import annotations
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi_csrf_protect import CsrfProtect
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import HTMLResponse
from backend.app.infrastructure.database.session import get_async_session
from backend.app.modules.auth.dependencies import get_current_user
from backend.app.modules.games.errors import GameAccessDenied, GameNotFound
from backend.app.modules.games.models.lobby import Game
from backend.app.modules.games.services import lobby_service
from backend.app.modules.maps.errors import MapAccessDenied
from backend.app.modules.maps.services import map_management_service as management
from backend.app.modules.users.models.user import User
from backend.app.web.exception_handlers import MapErrorRoute
from backend.app.web.rendering import get_page_settings, render_page


router = APIRouter(prefix="/maps", tags=["map-pages"], route_class=MapErrorRoute)

PageUser = Annotated[User, Depends(get_current_user)]
PageSession = Annotated[AsyncSession, Depends(get_async_session)]
PageCsrf = Annotated[CsrfProtect, Depends()]

async def _get_page_game(session: AsyncSession, game_id: UUID, user_id: UUID) -> Game:
	"""Преобразовать ошибки зависимости лобби только на HTTP-границе."""
	try:
		return await lobby_service.get_game(session, game_id, user_id)
	except GameNotFound as error:
		raise HTTPException(status_code=404, detail=str(error)) from None
	except GameAccessDenied as error:
		raise HTTPException(status_code=403, detail=str(error)) from None

@router.get("", response_class=HTMLResponse, name="maps_page_get", operation_id="getMapsPage")
async def get_maps_page(request: Request, user: PageUser, session: PageSession, csrf_protect: PageCsrf, game_id: UUID | None = None) -> HTMLResponse:
	games = await lobby_service.list_games_for_user(session, user.id)
	selected_game = None
	campaign_maps = []
	can_manage_maps = False

	if game_id is not None:
		selected_game = await _get_page_game(session, game_id, user.id)
		can_manage_maps = selected_game.master_id == user.id

		if can_manage_maps:
			campaign_maps = await management.list_maps_for_game(session, selected_game.id, user.id)

	context = {
		"user": user,
		"games": games,
		"selected_game": selected_game,
		"campaign_maps": campaign_maps,
		"can_manage_maps": can_manage_maps,
	}
	return render_page(request, "maps/maps.html", context, csrf_protect)

@router.get("/create", response_class=HTMLResponse, name="map_create_page_get", operation_id="getMapCreatePage")
async def get_map_create_page(request: Request, game_id: UUID, user: PageUser, session: PageSession, csrf_protect: PageCsrf) -> HTMLResponse:
	selected_game = await _get_page_game(session, game_id, user.id)

	if selected_game.master_id != user.id:
		raise MapAccessDenied("Только мастер игры может создавать карты")

	context = {
		"user": user,
		"selected_game": selected_game,
		"map_image_max_bytes": get_page_settings(request).MAP_IMAGE_MAX_BYTES,
	}
	return render_page(request, "maps/map_create.html", context, csrf_protect)

@router.get("/{map_id}/edit", response_class=HTMLResponse, name="map_edit_page_get", operation_id="getMapEditPage")
async def get_map_edit_page(request: Request, map_id: UUID, user: PageUser, session: PageSession, csrf_protect: PageCsrf) -> HTMLResponse:
	campaign_map = await management.get_map(session, map_id, user.id)
	context = {
		"user": user,
		"campaign_map": campaign_map,
		"map_image_max_bytes": get_page_settings(request).MAP_IMAGE_MAX_BYTES,
	}
	return render_page(request, "maps/map_edit.html", context, csrf_protect)

@router.get("/{map_id}/view", response_class=HTMLResponse, name="map_view_page_get", operation_id="getMapViewPage")
async def get_map_view_page(request: Request, map_id: UUID, user: PageUser, session: PageSession, csrf_protect: PageCsrf) -> HTMLResponse:
	campaign_map = await management.get_map(session, map_id, user.id)
	target_games = await management.list_target_games(session, user.id, campaign_map.game_id)
	context = {
		"user": user,
		"campaign_map": campaign_map,
		"target_games": target_games,
	}
	return render_page(request, "maps/map_view.html", context, csrf_protect)