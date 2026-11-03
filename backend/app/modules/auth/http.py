# backend/app/modules/auth/http.py

"""HTTP-адаптеры модуля авторизации."""

from collections.abc import Callable, Coroutine
from typing import Any
from fastapi import Depends, Request
from fastapi.routing import APIRoute
from fastapi_csrf_protect.exceptions import CsrfProtectError
from starlette.responses import JSONResponse, Response
from backend.app.core.settings import WebAppSettings
from backend.app.modules.auth.errors import AccountLocked, AccountNotFound, AuthError, InvalidCredentials, InvalidSession, MailDeliveryError, RegistrationConflict
from backend.app.modules.auth.services.notifications import AuthNotifications


RequestHandler = Callable[[Request], Coroutine[Any, Any, Response]]

def get_auth_settings(request: Request) -> WebAppSettings:
	"""Получить настройки, подключённые при сборке приложения."""
	settings = getattr(request.app.state, "settings", None)
	if not isinstance(settings, WebAppSettings):
		raise RuntimeError("Настройки не подключены к состоянию приложения")
	return settings

def get_auth_notifications(settings: WebAppSettings = Depends(get_auth_settings)) -> AuthNotifications:
	"""Создать адаптер писем без подключения к SMTP при импорте."""
	return AuthNotifications(settings)

def auth_error_response(error: AuthError) -> JSONResponse:
	"""Преобразовать ожидаемый отказ в безопасный JSON."""
	status_code = 400
	content: dict[str, object] = {"error": error.message}
	headers: dict[str, str] = {}

	if isinstance(error, AccountLocked):
		status_code = 429
		content["retry_after_seconds"] = error.retry_after_seconds
		headers["Retry-After"] = str(error.retry_after_seconds)
	elif isinstance(error, RegistrationConflict):
		status_code = 409
	elif isinstance(error, MailDeliveryError):
		status_code = 503
	elif isinstance(error, AccountNotFound):
		status_code = 404
	elif isinstance(error, (InvalidCredentials, InvalidSession)):
		status_code = 401

	return JSONResponse(status_code=status_code, content=content, headers=headers)

class AuthErrorRoute(APIRoute):
	"""Обрабатывать прикладные отказы и запрещать кеширование ответов авторизации."""

	def get_route_handler(self) -> RequestHandler:
		original_handler = super().get_route_handler()

		async def route_handler(request: Request) -> Response:
			try:
				response = await original_handler(request)
			except AuthError as exc:
				response = auth_error_response(exc)
			except CsrfProtectError:
				response = JSONResponse(
					status_code=403, content={"detail": "Не удалось проверить защиту запроса. Обновите страницу и попробуйте снова."},
				)

			response.headers["Cache-Control"] = "no-store"
			response.headers["Referrer-Policy"] = "no-referrer"
			return response

		return route_handler