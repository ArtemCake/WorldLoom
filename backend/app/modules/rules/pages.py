# backend/app/modules/rules/pages.py

"""HTML-страница каталога опубликованных правил."""

from typing import Annotated
from fastapi import APIRouter, Depends, Request
from fastapi_csrf_protect import CsrfProtect
from starlette.responses import HTMLResponse
from backend.app.modules.auth.dependencies import get_optional_user
from backend.app.modules.rules.http import RulesSession, rules_operation
from backend.app.modules.rules.services import system_catalog
from backend.app.modules.users.models.user import User
from backend.app.web.rendering import render_page
from backend.app.modules.rules.http import RulesEditor


OptionalUser = Annotated[User | None, Depends(get_optional_user)]
PageCsrf = Annotated[CsrfProtect, Depends()]

router = APIRouter(prefix="/rules", tags=["rules-pages"])

@router.get("/workspace", response_class=HTMLResponse, name="rules_workspace_get")
async def workspace_page(request: Request, user: RulesEditor, csrf_protect: PageCsrf, session: RulesSession) -> HTMLResponse:
	async with rules_operation(session):
		systems = await system_catalog.list_active_system_options(session)
		context = {"user": user, "rule_systems": systems}
		response = render_page(request, "rules/workspace.html", context, csrf_protect)

	response.headers["Cache-Control"] = "no-store"
	return response

@router.get("/catalog", response_class=HTMLResponse, name="rules_catalog_get")
async def catalog_page(request: Request, user: OptionalUser, csrf_protect: PageCsrf, session: RulesSession) -> HTMLResponse:
	context = {"user": user, "rule_systems": []}

	if user is not None:
		async with rules_operation(session):
			context["rule_systems"] = await system_catalog.list_active_system_options(session)
			response = render_page(request, "rules/catalog.html", context, csrf_protect)
	else:
		response = render_page(request, "rules/catalog.html", context, csrf_protect)

	response.headers["Cache-Control"] = "no-store"
	return response