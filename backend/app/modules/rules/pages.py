# backend/app/modules/rules/pages.py

"""HTML-страница каталога опубликованных правил."""

from typing import Annotated
from fastapi import APIRouter, Depends, Request
from fastapi_csrf_protect import CsrfProtect
from starlette.responses import HTMLResponse
from backend.app.modules.auth.dependencies import get_optional_user
from backend.app.modules.users.models.user import User
from backend.app.web.rendering import render_page


OptionalUser = Annotated[User | None, Depends(get_optional_user)]
PageCsrf = Annotated[CsrfProtect, Depends()]

router = APIRouter(prefix="/rules", tags=["rules-pages"])

@router.get("/catalog", response_class=HTMLResponse, name="rules_catalog_get")
async def catalog_page(request: Request, user: OptionalUser, csrf_protect: PageCsrf) -> HTMLResponse:
	response = render_page(request, "rules/catalog.html", {"user": user}, csrf_protect)
	response.headers["Cache-Control"] = "no-store"
	return response
