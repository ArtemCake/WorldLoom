# backend/app/web/pages.py

"""Главная страница и сборка HTML-маршрутов модулей без запуска приложения."""

from typing import Annotated
from fastapi import APIRouter, Depends, Request
from fastapi_csrf_protect import CsrfProtect
from starlette.responses import HTMLResponse
from backend.app.modules.auth.dependencies import get_optional_user
from backend.app.modules.auth.pages import router as auth_pages_router
from backend.app.modules.games.pages import router as games_pages_router
from backend.app.modules.legal.pages import router as legal_pages_router
from backend.app.modules.maps.pages import router as maps_pages_router
from backend.app.modules.users.models.user import User
from backend.app.modules.users.pages import router as users_pages_router
from backend.app.web.rendering import render_page
from backend.app.modules.game_systems.pages import router as game_systems_pages_router
from backend.app.modules.characters.api.api import router as characters_router


router = APIRouter()

OptionalUser = Annotated[User | None, Depends(get_optional_user)]
PageCsrf = Annotated[CsrfProtect, Depends()]

@router.get("/", response_class=HTMLResponse, name="main_page_get")
async def get_main_page(request: Request, user: OptionalUser, csrf_protect: PageCsrf) -> HTMLResponse:
	return render_page(request, "home/index.html", {"user": user}, csrf_protect)

router.include_router(auth_pages_router)
router.include_router(users_pages_router)
router.include_router(games_pages_router)
router.include_router(maps_pages_router)
router.include_router(legal_pages_router)
router.include_router(game_systems_pages_router)
router.include_router(characters_router)