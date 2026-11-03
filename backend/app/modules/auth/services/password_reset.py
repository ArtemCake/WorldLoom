# backend/app/modules/auth/services/password_reset.py

"""Запрос восстановления и установка нового пароля по одноразовой ссылке."""

from __future__ import annotations

from datetime import datetime, timezone
from hmac import compare_digest

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.settings import WebAppSettings
from backend.app.modules.auth.errors import AuthError
from backend.app.modules.auth.schemas import validate_password_complexity
from backend.app.modules.auth.services.notifications import AuthNotifications
from backend.app.modules.auth.services.passwords import hash_password
from backend.app.modules.auth.services.tokens import PASSWORD_RESET_LIFETIME, create_password_reset_token, password_fingerprint, verify_token
from backend.app.modules.users.services.users import get_user_by_email, get_user_by_id

PASSWORD_RESET_REQUEST_MESSAGE = "Если такой email зарегистрирован, на него отправлена ссылка для восстановления пароля."

class InvalidPasswordReset(AuthError):
	code = "invalid_password_reset"
	default_message = "Ссылка недействительна или устарела."

class InvalidNewPassword(AuthError):
	code = "invalid_new_password"
	default_message = "Новый пароль не соответствует требованиям."

async def request_password_reset(
		session: AsyncSession, email: str, *, settings: WebAppSettings, notifications: AuthNotifications,
) -> None:
	"""Не возвращать наружу наличие аккаунта или результат отправки письма."""
	try:
		user = await get_user_by_email(session, email)
		if user is None or not user.is_active or not user.password_hash:
			await session.rollback()
			return

		recipient = user.email
		reset_token = create_password_reset_token(user, settings=settings)

		# Освободить транзакцию чтения до сетевой операции SMTP.
		await session.rollback()
	except Exception:
		await session.rollback()
		raise

	valid_minutes = int(PASSWORD_RESET_LIFETIME.total_seconds() // 60)
	await notifications.send_password_reset(recipient, reset_token, valid_minutes=valid_minutes)

async def reset_password(session: AsyncSession, token: str, new_password: str, *, settings: WebAppSettings) -> None:
	"""Проверить ссылку и атомарно заменить пароль с отзывом активной сессии."""
	try:
		payload = verify_token(token, purpose="password_reset", settings=settings)
		if payload is None:
			raise InvalidPasswordReset()

		user = await get_user_by_id(session, payload["sub"], for_update=True)
		if user is None or not user.is_active or not user.password_hash:
			raise InvalidPasswordReset()

		supplied_fingerprint = payload.get("pwfp")
		current_fingerprint = password_fingerprint(user.password_hash)
		if not isinstance(supplied_fingerprint, str):
			raise InvalidPasswordReset()

		if not compare_digest(supplied_fingerprint.encode("utf-8"), current_fingerprint.encode("utf-8")):
			raise InvalidPasswordReset("Ссылка уже использована или устарела.")

		if not 8 <= len(new_password) <= 128:
			raise InvalidNewPassword("Пароль должен быть от 8 до 128 символов.")

		complexity_error = validate_password_complexity(new_password)
		if complexity_error:
			raise InvalidNewPassword(complexity_error)

		user.password_hash = hash_password(new_password)
		user.active_session_token = None
		user.updated_at = datetime.now(timezone.utc)
		await session.commit()
	except Exception:
		await session.rollback()
		raise