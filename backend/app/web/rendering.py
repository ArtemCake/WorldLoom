# backend/app/web/rendering.py

"""Создание шаблонов и общий рендеринг HTML-страниц."""

from __future__ import annotations
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from fastapi import Request
from fastapi.templating import Jinja2Templates
from fastapi_csrf_protect import CsrfProtect
from starlette.responses import HTMLResponse
from backend.app.core.settings import WebAppSettings
from backend.app.web.assets import b64encode_filter, create_static_url
from backend.app.web.csrf import apply_csrf_tokens, ensure_csrf_tokens


def create_templates(settings: WebAppSettings, *, directory: Path | None = None) -> Jinja2Templates:
	"""Создать окружение шаблонов при явной сборке приложения."""
	templates_dir = directory if directory is not None else Path(settings.BASE_DIR) / "frontend" / "templates"
	templates_dir = templates_dir.resolve()

	if not templates_dir.is_dir():
		raise RuntimeError("Каталог HTML-шаблонов не найден")

	templates = Jinja2Templates(directory=str(templates_dir))
	asset_url = create_static_url()
	templates.env.filters["static_url"] = asset_url
	templates.env.globals["static_url"] = asset_url
	templates.env.filters["b64encode"] = b64encode_filter
	return templates

def get_page_settings(request: Request) -> WebAppSettings:
	"""Получить уже подключённые настройки без повторного чтения окружения."""
	settings = getattr(request.app.state, "settings", None)

	if not isinstance(settings, WebAppSettings):
		raise RuntimeError("Настройки не подключены к состоянию приложения")

	return settings

def render_page(request: Request, template_name: str, context: Mapping[str, Any], csrf_protect: CsrfProtect, *, status_code: int = 200) -> HTMLResponse:
	"""Отрендерить страницу и добавить защитные данные в тот же ответ."""
	templates = getattr(request.app.state, "templates", None)

	if not isinstance(templates, Jinja2Templates):
		raise RuntimeError("HTML-шаблоны не подключены к состоянию приложения")

	settings = get_page_settings(request)
	tokens = ensure_csrf_tokens(request, csrf_protect)
	page_context = {
		**context,
		"request": request,
		"project_name": settings.PROJECT_NAME,
		"csrf_token": tokens.token,
	}
	response = templates.TemplateResponse(
		request=request,
		name=template_name,
		context=page_context,
		status_code=status_code,
	)
	apply_csrf_tokens(response, csrf_protect, tokens)
	response.headers["X-Content-Type-Options"] = "nosniff"
	return response