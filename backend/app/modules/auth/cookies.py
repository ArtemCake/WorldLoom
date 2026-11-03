# backend/app/modules/auth/cookies.py

"""Установка и удаление авторизационных cookie."""

from starlette.responses import Response
from backend.app.core.settings import WebAppSettings
from backend.app.modules.auth.services.tokens import REFRESH_TOKEN_LIFETIME


def set_auth_cookie(response: Response, key: str, value: str, max_age: int, *, settings: WebAppSettings) -> None:
	"""Установить cookie с параметрами прежней реализации."""
	response.set_cookie(
		key=key, value=value, max_age=max_age, httponly=True, secure=bool(settings.SECURE_COOKIES), samesite="lax", path="/",
	)

def clear_auth_cookie(response: Response, key: str, *, settings: WebAppSettings) -> None:
	"""Удалить cookie с теми же path и параметрами безопасности."""
	response.delete_cookie(key=key, path="/", httponly=True, secure=bool(settings.SECURE_COOKIES), samesite="lax")

def set_auth_cookies(response: Response, tokens: dict[str, str], *, settings: WebAppSettings) -> None:
	"""Установить стандартную пару cookie после входа или обновления сессии."""
	access_token = tokens["access_token"]
	refresh_token = tokens["refresh_token"]
	access_max_age = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
	refresh_max_age = int(REFRESH_TOKEN_LIFETIME.total_seconds())

	set_auth_cookie(response, "access_token", access_token, access_max_age, settings=settings)
	set_auth_cookie(response, "refresh_token", refresh_token, refresh_max_age, settings=settings)

def clear_auth_cookies(response: Response, *, settings: WebAppSettings) -> None:
	"""Удалить обе авторизационные cookie."""
	clear_auth_cookie(response, "access_token", settings=settings)
	clear_auth_cookie(response, "refresh_token", settings=settings)