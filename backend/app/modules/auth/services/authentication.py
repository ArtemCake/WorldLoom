# backend/app/modules/auth/services/authentication.py

"""Проверка пароля, блокировка входа и управление единственной активной сессией."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from hmac import compare_digest
from math import ceil
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import lazyload

from backend.app.core.crypto import hash_email
from backend.app.core.settings import WebAppSettings
from backend.app.modules.auth.errors import AccountLocked, AccountNotFound, InvalidCredentials, InvalidSession
from backend.app.modules.auth.services.passwords import verify_password
from backend.app.modules.auth.services.tokens import InvalidRefreshToken, create_jwt_pair, create_mfa_pending_token, decode_refresh_token
from backend.app.modules.users.models.user import User

@dataclass(frozen=True)
class PasswordLoginResult:
	"""Результат проверки пароля: готовые токены либо ожидание второго фактора."""

	tokens: dict[str, str] | None = field(default=None, repr=False)
	mfa_token: str | None = field(default=None, repr=False)

	def __post_init__(self) -> None:
		if (self.tokens is None) == (self.mfa_token is None):
			raise ValueError("Результат входа должен содержать либо пару токенов, либо токен ожидания MFA")

	@property
	def mfa_required(self) -> bool:
		return self.mfa_token is not None

def _as_utc(value: datetime) -> datetime:
	"""Считать старые значения без часового пояса временем UTC."""
	if value.tzinfo is None:
		return value.replace(tzinfo=timezone.utc)
	return value.astimezone(timezone.utc)

def _session_matches(user: User, session_token: str) -> bool:
	"""Сравнить идентификаторы сессии без обычного строкового сравнения."""
	active_token = user.active_session_token
	if not isinstance(active_token, str) or not active_token:
		return False
	if not isinstance(session_token, str) or not session_token:
		return False
	return compare_digest(active_token.encode("utf-8"), session_token.encode("utf-8"))

async def _get_user_by_email_for_update(session: AsyncSession, email: str) -> User | None:
	"""Найти пользователя по прежнему HMAC email и заблокировать его строку."""
	statement = (
		select(User)
		.where(User.email_hash == hash_email(email))
		.options(lazyload("*"))
		.execution_options(populate_existing=True)
		.with_for_update()
	)
	result = await session.execute(statement)
	return result.scalar_one_or_none()

async def _get_user_by_id_for_update(session: AsyncSession, user_id: UUID) -> User | None:
	"""Перечитать актуальное состояние пользователя с блокировкой строки."""
	statement = (
		select(User)
		.where(User.id == user_id)
		.options(lazyload("*"))
		.execution_options(populate_existing=True)
		.with_for_update()
	)
	result = await session.execute(statement)
	return result.scalar_one_or_none()

def _check_login_lockout(user: User, now: datetime) -> None:
	"""Отклонить вход, пока не истёк срок блокировки."""
	if user.locked_until is None:
		return

	remaining_seconds = (_as_utc(user.locked_until) - now).total_seconds()
	if remaining_seconds > 0:
		raise AccountLocked(ceil(remaining_seconds))

def _register_failed_login(user: User, now: datetime, *, settings: WebAppSettings) -> None:
	"""Изменить счётчик и срок блокировки в текущей транзакции."""
	user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
	if user.failed_login_attempts >= settings.LOGIN_MAX_FAILED_ATTEMPTS:
		user.locked_until = now + timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)

def _reset_login_lockout(user: User) -> None:
	"""Сбросить счётчик и блокировку после правильного пароля."""
	user.failed_login_attempts = 0
	user.locked_until = None

async def issue_login_session(session: AsyncSession, user: User, *, settings: WebAppSettings) -> dict[str, str]:
	"""Подготовить пару JWT и новый sid после завершённой проверки входа.

	Для аккаунта с MFA вызывается только после проверки второго фактора.
	Вызывающий код обязан держать блокировку строки пользователя.
	Функция не выполняет commit: токены нельзя отдавать до фиксации транзакции.
	"""
	if not user.is_active:
		raise InvalidSession()

	new_session_token = secrets.token_urlsafe(64)
	tokens = await create_jwt_pair(user, session_token=new_session_token, settings=settings)

	user.active_session_token = new_session_token
	user.updated_at = datetime.now(timezone.utc)
	session.add(user)

	return tokens

async def login_with_password(session: AsyncSession, email: str, password: str, *, settings: WebAppSettings) -> PasswordLoginResult:
	"""Проверить пароль, зафиксировать результат и при необходимости запросить MFA."""
	try:
		user = await _get_user_by_email_for_update(session, email)
		if user is None:
			raise AccountNotFound()

		now = datetime.now(timezone.utc)
		_check_login_lockout(user, now)

		password_is_valid = bool(user.password_hash) and verify_password(password, user.password_hash)
		if not password_is_valid or not user.is_active:
			_register_failed_login(user, datetime.now(timezone.utc), settings=settings)
			await session.commit()
			raise InvalidCredentials()

		_reset_login_lockout(user)

		if user.is_2fa_enabled:
			mfa_token = create_mfa_pending_token(user.id, settings=settings)
			await session.commit()
			return PasswordLoginResult(mfa_token=mfa_token)

		tokens = await issue_login_session(session, user, settings=settings)
		await session.commit()
		return PasswordLoginResult(tokens=tokens)
	except Exception:
		await session.rollback()
		raise

async def refresh_login_session(session: AsyncSession, refresh_token: str, *, settings: WebAppSettings) -> dict[str, str]:
	"""Проверить refresh-токен и атомарно заменить идентификатор сессии."""
	try:
		try:
			identity = decode_refresh_token(refresh_token, secret_key=settings.SECRET_KEY, algorithm=settings.ALGORITHM)
		except InvalidRefreshToken:
			raise InvalidSession("Недействительный refresh-токен.") from None

		user = await _get_user_by_id_for_update(session, identity.user_id)
		if user is None or not user.is_active or not _session_matches(user, identity.session_id):
			raise InvalidSession()

		tokens = await issue_login_session(session, user, settings=settings)
		await session.commit()
		return tokens
	except Exception:
		await session.rollback()
		raise

async def logout_session(session: AsyncSession, user_id: UUID, session_token: str) -> None:
	"""Завершить указанную сессию, не затрагивая более новую сессию пользователя."""
	try:
		user = await _get_user_by_id_for_update(session, user_id)
		if user is None or not user.is_active or not _session_matches(user, session_token):
			raise InvalidSession()

		user.active_session_token = None
		user.updated_at = datetime.now(timezone.utc)
		await session.commit()
	except Exception:
		await session.rollback()
		raise