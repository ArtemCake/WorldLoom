# backend/app/modules/auth/dependencies.py

"""HTTP-зависимости авторизации и проверки подтверждения почты."""

from __future__ import annotations
from hmac import compare_digest
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import lazyload
from backend.app.core.settings import WebAppSettings
from backend.app.infrastructure.database.session import (get_async_session)
from backend.app.modules.auth.services.tokens import (InvalidAccessToken, decode_access_token)
from backend.app.modules.users.models.user import User


def _credentials_error() -> HTTPException:
	return HTTPException(
		status_code=status.HTTP_401_UNAUTHORIZED,
		detail="Не удалось подтвердить авторизацию",
		headers={"WWW-Authenticate": "Bearer"},
	)

def _get_settings(request: Request) -> WebAppSettings:
	"""Получить настройки, явно установленные сборкой приложения."""
	settings = getattr(request.app.state, "settings", None)

	if not isinstance(settings, WebAppSettings):
		raise RuntimeError(
			"Настройки не подключены к состоянию приложения"
		)

	return settings

def _extract_access_token(request: Request) -> str | None:
	"""Получить Bearer-токен или, при отсутствии заголовка, cookie.

	Явно переданный некорректный Authorization не заменяется cookie.
	"""
	headers = request.headers.getlist("authorization")

	if headers:
		if len(headers) != 1:
			raise _credentials_error()

		parts = headers[0].split()

		if (
				len(parts) != 2
				or parts[0].lower() != "bearer"
				or not parts[1]
		):
			raise _credentials_error()

		return parts[1]

	token = request.cookies.get("access_token")

	if token is None:
		return None

	if not token.strip():
		raise _credentials_error()

	return token

async def get_current_user(request: Request, session: AsyncSession = Depends(get_async_session)) -> User:
	"""Проверить JWT, активность пользователя и действующий sid.

	Ничего не изменяет и не завершает транзакцию.
	"""
	token = _extract_access_token(request)

	if token is None:
		raise _credentials_error()

	settings = _get_settings(request)

	try:
		identity = decode_access_token(
			token,
			secret_key=settings.SECRET_KEY,
			algorithm=settings.ALGORITHM,
		)
	except InvalidAccessToken:
		raise _credentials_error() from None

	user = (
		await session.execute(
			select(User)
			.where(User.id == identity.user_id)
			.options(lazyload("*"))
			.execution_options(populate_existing=True)
		)
	).scalar_one_or_none()

	if user is None or not user.is_active:
		raise _credentials_error()

	active_session = user.active_session_token

	if (
			not isinstance(active_session, str)
			or not active_session
			or not compare_digest(
		active_session.encode("utf-8"),
		identity.session_id.encode("utf-8"),
	)
	):
		raise _credentials_error()

	return user

async def get_optional_user(request: Request, session: AsyncSession = Depends(get_async_session)) -> User | None:
	"""Вернуть пользователя либо None при отсутствии авторизации.

	Ошибки конфигурации и БД не маскируются под анонимный доступ.
	"""
	try:
		return await get_current_user(request, session)
	except HTTPException as exc:
		if exc.status_code != status.HTTP_401_UNAUTHORIZED:
			raise
		return None

async def require_verified_user(user: User = Depends(get_current_user)) -> User:
	"""Дополнительно потребовать подтверждённую почту."""
	if not user.is_email_verified:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail=(
				"Подтвердите email, чтобы получить доступ "
				"к этой операции"
			),
		)

	return user