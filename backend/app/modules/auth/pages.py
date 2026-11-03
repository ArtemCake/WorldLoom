# backend/app/modules/auth/pages.py

"""HTML-маршруты входа, регистрации и восстановления пароля."""

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi_csrf_protect import CsrfProtect
from jinja2 import TemplateNotFound
from starlette.responses import HTMLResponse, RedirectResponse, Response
from backend.app.modules.auth.dependencies import get_optional_user
from backend.app.modules.auth.http import AuthErrorRoute
from backend.app.modules.users.models.user import User
from backend.app.web.rendering import render_page


router = APIRouter(tags=["auth-pages"], route_class=AuthErrorRoute)

OptionalUser = Annotated[User | None, Depends(get_optional_user)]
PageCsrf = Annotated[CsrfProtect, Depends()]

def _render_auth_page(request: Request, user: User | None, csrf_protect: CsrfProtect, template_name: str, *, reset_token: str | None = None) -> Response:
	"""Перенаправить авторизованного пользователя или показать страницу с CSRF."""
	if user is not None:
		return RedirectResponse(url="/profile", status_code=302)

	context: dict[str, object] = {"user": None}
	if reset_token is not None:
		context["reset_token"] = reset_token

	try:
		return render_page(request, template_name, context, csrf_protect)
	except TemplateNotFound:
		raise HTTPException(status_code=404, detail="Шаблон страницы авторизации не найден.") from None

@router.get("/login", response_class=HTMLResponse, name="login_page_get")
async def get_login_page(request: Request, user: OptionalUser, csrf_protect: PageCsrf) -> Response:
	return _render_auth_page(request, user, csrf_protect, "auth/login.html")

@router.get("/register", response_class=HTMLResponse, name="register_page_get")
async def get_register_page(request: Request, user: OptionalUser, csrf_protect: PageCsrf) -> Response:
	return _render_auth_page(request, user, csrf_protect, "auth/register.html")

@router.get("/forgot-password", response_class=HTMLResponse, name="forgot_password_page_get")
async def get_forgot_password_page(request: Request, user: OptionalUser, csrf_protect: PageCsrf) -> Response:
	return _render_auth_page(request, user, csrf_protect, "auth/forgot_password.html")

@router.get("/reset-password", response_class=HTMLResponse, name="reset_password_page_get")
async def get_reset_password_page(request: Request, user: OptionalUser, csrf_protect: PageCsrf, token: str = "") -> Response:
	return _render_auth_page(request, user, csrf_protect, "auth/reset_password.html", reset_token=token)