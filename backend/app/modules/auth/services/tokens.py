# backend/app/modules/auth/services/tokens.py

"""Выпуск и проверка JWT без HTTP, запросов к БД и загрузки настроек при импорте."""

from __future__ import annotations
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any
from uuid import UUID
from jose import JWTError, jwt
from backend.app.core.settings import WebAppSettings
if TYPE_CHECKING:
	from backend.app.modules.users.models.user import User


REFRESH_TOKEN_LIFETIME = timedelta(days=7)
EMAIL_VERIFICATION_LIFETIME = timedelta(hours=24)
PASSWORD_RESET_LIFETIME = timedelta(minutes=30)
MFA_PENDING_LIFETIME = timedelta(minutes=5)

class InvalidToken(ValueError):
	"""Подпись, срок действия или содержимое токена не прошли проверку."""

class InvalidAccessToken(InvalidToken):
	"""Токен не подходит для авторизации запроса."""

class InvalidRefreshToken(InvalidToken):
	"""Токен не подходит для обновления сессии."""

@dataclass(frozen=True)
class AccessIdentity:
	"""Идентификаторы из access-токена; действительность сессии проверяется по БД."""

	user_id: UUID
	session_id: str = field(repr=False)

@dataclass(frozen=True)
class RefreshIdentity:
	"""Идентификаторы из refresh-токена; сами по себе не подтверждают активность сессии."""

	user_id: UUID
	session_id: str = field(repr=False)

def _validate_jwt_config(secret_key: str, algorithm: str) -> None:
	"""Не допускать проверки или выпуска токенов с некорректной конфигурацией."""
	if not secret_key or not algorithm or algorithm.lower() == "none":
		raise RuntimeError("Некорректная конфигурация JWT")

def _normalize_subject(user_id: str | UUID) -> str:
	"""Привести идентификатор пользователя к строковому UUID."""
	return str(UUID(str(user_id)))

def _encode_timed_payload(payload: dict[str, Any], expires_delta: timedelta, settings: WebAppSettings) -> str:
	"""Добавить срок действия и подписать полезную нагрузку."""
	_validate_jwt_config(settings.SECRET_KEY, settings.ALGORITHM)

	if expires_delta.total_seconds() <= 0:
		raise ValueError("Срок действия токена должен быть положительным")

	claims = {**payload, "exp": datetime.now(timezone.utc) + expires_delta}
	return jwt.encode(claims, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def _decode_payload(token: str, *, secret_key: str, algorithm: str) -> dict[str, Any]:
	"""Проверить подпись и обязательные exp/sub до чтения назначения токена."""
	_validate_jwt_config(secret_key, algorithm)

	if not isinstance(token, str) or not token.strip():
		raise InvalidToken("Недействительный токен")

	try:
		payload = jwt.decode(
			token, secret_key, algorithms=[algorithm], options={"require_exp": True, "require_sub": True},
		)
	except JWTError as exc:
		raise InvalidToken("Недействительный токен") from exc

	return payload

def _decode_session_claims(token: str, token_type: str, *, secret_key: str, algorithm: str) -> tuple[UUID, str]:
	"""Проверить назначение сессионного токена и извлечь идентификаторы."""
	payload = _decode_payload(token, secret_key=secret_key, algorithm=algorithm)

	if payload.get("type") != token_type:
		raise InvalidToken("Неверное назначение токена")

	subject = payload.get("sub")
	session_id = payload.get("sid")

	if not isinstance(subject, str) or not subject.strip() or not isinstance(session_id, str) or not session_id.strip():
		raise InvalidToken("Недействительные идентификаторы токена")

	try:
		user_id = UUID(subject)
	except ValueError as exc:
		raise InvalidToken("Недействительный идентификатор пользователя") from exc

	return user_id, session_id

def decode_access_token(token: str, *, secret_key: str, algorithm: str) -> AccessIdentity:
	"""Проверить access-токен без обращения к базе данных."""
	try:
		user_id, session_id = _decode_session_claims(token, "access", secret_key=secret_key, algorithm=algorithm)
	except InvalidToken as exc:
		raise InvalidAccessToken("Недействительный access-токен") from exc

	return AccessIdentity(user_id=user_id, session_id=session_id)

def decode_refresh_token(token: str, *, secret_key: str, algorithm: str) -> RefreshIdentity:
	"""Проверить refresh-токен без обращения к базе данных."""
	try:
		user_id, session_id = _decode_session_claims(token, "refresh", secret_key=secret_key, algorithm=algorithm)
	except InvalidToken as exc:
		raise InvalidRefreshToken("Недействительный refresh-токен") from exc

	return RefreshIdentity(user_id=user_id, session_id=session_id)

async def create_jwt_pair(user_obj_or_id: User | str | UUID, expires_delta: timedelta | None = None, session_token: str | None = None, *,
    settings: WebAppSettings) -> dict[str, str]:
	"""Создать access/refresh с общим sid; не сохранять сессию и не изменять БД."""
	if hasattr(user_obj_or_id, "id"):
		if not hasattr(user_obj_or_id, "is_active") or not hasattr(user_obj_or_id, "is_email_verified"):
			raise PermissionError("У объекта пользователя отсутствуют признаки безопасности")

		if not user_obj_or_id.is_active:
			raise PermissionError("Нельзя создать токены для неактивного пользователя")

		subject = _normalize_subject(user_obj_or_id.id)
	else:
		subject = _normalize_subject(user_obj_or_id)

	if not isinstance(session_token, str) or not session_token.strip():
		raise ValueError("Для выпуска токенов требуется идентификатор сессии")

	if expires_delta is None:
		expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

	access_data = {"sub": subject, "type": "access", "sid": session_token}
	refresh_data = {"sub": subject, "type": "refresh", "sid": session_token}

	return {
		"access_token": _encode_timed_payload(access_data, expires_delta, settings),
		"refresh_token": _encode_timed_payload(refresh_data, REFRESH_TOKEN_LIFETIME, settings),
	}

def create_verification_token(user_id: str | UUID, expires_delta: timedelta | None = None, *, email_hash: str, verification_version: str = "",
    settings: WebAppSettings) -> str:
	"""Создать подтверждение для конкретного email и версии его изменения."""
	if not isinstance(email_hash, str) or not email_hash:
		raise ValueError("Для подтверждения требуется поисковый HMAC email")

	if not isinstance(verification_version, str):
		raise ValueError("Некорректная версия подтверждения почты")

	if expires_delta is None:
		expires_delta = EMAIL_VERIFICATION_LIFETIME

	payload = {
		"sub": _normalize_subject(user_id),
		"purpose": "email_verification",
		"email_hash": email_hash,
		"verification_version": verification_version,
	}
	return _encode_timed_payload(payload, expires_delta, settings)

def password_fingerprint(password_hash: str | None) -> str:
	"""Отпечаток хеша для проверки одноразовости ссылки сброса пароля."""
	return hashlib.sha256((password_hash or "").encode()).hexdigest()[:16]

def create_password_reset_token(user: User, expires_delta: timedelta | None = None, *, settings: WebAppSettings) -> str:
	"""Создать токен сброса, привязанный к текущему хешу пароля."""
	if expires_delta is None:
		expires_delta = PASSWORD_RESET_LIFETIME

	payload = {"sub": _normalize_subject(user.id), "purpose": "password_reset", "pwfp": password_fingerprint(user.password_hash)}
	return _encode_timed_payload(payload, expires_delta, settings)

def create_mfa_pending_token(user_id: str | UUID, expires_delta: timedelta | None = None, *, settings: WebAppSettings) -> str:
	"""Создать временный токен ожидания MFA, не предоставляющий доступ к API."""
	if expires_delta is None:
		expires_delta = MFA_PENDING_LIFETIME

	payload = {"sub": _normalize_subject(user_id), "purpose": "mfa_pending"}
	return _encode_timed_payload(payload, expires_delta, settings)

def verify_token(token: str, purpose: str = "email_verification", *, settings: WebAppSettings) -> dict[str, Any] | None:
	"""Проверить служебный токен; вернуть None при неверном назначении или содержимом."""
	try:
		payload = _decode_payload(token, secret_key=settings.SECRET_KEY, algorithm=settings.ALGORITHM)

		if payload.get("purpose") != purpose:
			return None

		_normalize_subject(payload["sub"])
	except (InvalidToken, ValueError, TypeError, KeyError):
		return None

	return payload