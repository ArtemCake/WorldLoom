# backend/app/modules/game_systems/pages.py

"""HTML-страницы каталога, просмотра и конструктора игровых систем."""

from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Request
from fastapi_csrf_protect import CsrfProtect
from starlette.responses import HTMLResponse
from backend.app.modules.auth.dependencies import get_optional_user
from backend.app.modules.users.models.user import User
from backend.app.web.rendering import render_page


OptionalUser = Annotated[User | None, Depends(get_optional_user)]
PageCsrf = Annotated[CsrfProtect, Depends()]

router = APIRouter(prefix="/game-systems/catalog", tags=["game-system-pages"])

def _render_system_page(request: Request, user: User | None, csrf_protect: CsrfProtect, page_mode: str,
                        system_id: UUID | None = None) -> HTMLResponse:
	context = {
		"user": user,
		"page_mode": page_mode,
		"system_id": str(system_id) if system_id is not None else "",
	}

	return render_page(request, "game_systems/game_systems.html", context, csrf_protect)

@router.get("", response_class=HTMLResponse, name="game_systems_catalog_get")
async def catalog_page(request: Request, user: OptionalUser, csrf_protect: PageCsrf) -> HTMLResponse:
	return _render_system_page(request, user, csrf_protect, "list")

@router.get("/new", response_class=HTMLResponse, name="game_systems_create_get")
async def create_page(request: Request, user: OptionalUser, csrf_protect: PageCsrf) -> HTMLResponse:
	return _render_system_page(request, user, csrf_protect, "create")

@router.get("/{system_id}/edit", response_class=HTMLResponse, name="game_systems_edit_get")
async def edit_page(system_id: UUID, request: Request, user: OptionalUser, csrf_protect: PageCsrf) -> HTMLResponse:
	return _render_system_page(request, user, csrf_protect, "edit", system_id)

@router.get("/{system_id}", response_class=HTMLResponse, name="game_systems_view_get")
async def view_page(system_id: UUID, request: Request, user: OptionalUser, csrf_protect: PageCsrf) -> HTMLResponse:
	return _render_system_page(request, user, csrf_protect, "view", system_id)