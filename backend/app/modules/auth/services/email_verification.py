# backend/app/modules/auth/services/email_verification.py

"""Подтверждение текущего адреса почты и повторная отправка письма."""

from hmac import compare_digest
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.logging import get_logger
from backend.app.core.settings import WebAppSettings
from backend.app.modules.auth.errors import AccountNotFound, MailDeliveryError
from backend.app.modules.auth.services.notifications import AuthNotifications
from backend.app.modules.auth.services.tokens import create_verification_token, verify_token
from backend.app.modules.users.models.user import User
from backend.app.modules.users.services.users import get_user_by_id


log = get_logger(__name__)

EMAIL_VERIFICATION_VERSION_KEY = "email_verification_version"

def build_email_verification_token(user: User, *, settings: WebAppSettings) -> str:
	"""Взять адрес и версию из актуального состояния пользователя."""
	version = (user.profile_settings or {}).get(EMAIL_VERIFICATION_VERSION_KEY, "")
	return create_verification_token(user.id, email_hash=user.email_hash, verification_version=version, settings=settings)

def _matches_claim(value: object, expected: str) -> bool:
	if not isinstance(value, str):
		return False
	return compare_digest(value.encode("utf-8"), expected.encode("utf-8"))

async def confirm_email(session: AsyncSession, token: str, *, settings: WebAppSettings) -> str:
	"""Подтвердить только текущий email; вернуть результат для перенаправления."""
	try:
		payload = verify_token(token, purpose="email_verification", settings=settings)
		if payload is None:
			await session.rollback()
			return "invalid"

		user = await get_user_by_id(session, payload["sub"], for_update=True)
		if user is None or not user.is_active:
			await session.rollback()
			return "notfound"

		version = (user.profile_settings or {}).get(EMAIL_VERIFICATION_VERSION_KEY, "")
		if not isinstance(version, str):
			raise RuntimeError("Некорректная версия подтверждения почты в профиле")

		address_matches = _matches_claim(payload.get("email_hash"), user.email_hash)
		version_matches = _matches_claim(payload.get("verification_version"), version)

		if not address_matches or not version_matches:
			await session.rollback()
			return "invalid"

		user.is_email_verified = True
		await session.commit()
		return "success"
	except Exception:
		await session.rollback()
		raise

async def resend_verification(
		session: AsyncSession, user_id: UUID, *, settings: WebAppSettings, notifications: AuthNotifications,
) -> bool:
	"""Вернуть False для подтверждённой почты, True после подтверждения отправки SMTP."""
	try:
		user = await get_user_by_id(session, user_id)
		if user is None or not user.is_active:
			raise AccountNotFound("Пользователь не найден.")

		if user.is_email_verified:
			await session.rollback()
			return False

		nickname = user.nickname
		recipient = user.email
		token = build_email_verification_token(user, settings=settings)
		await session.rollback()
	except Exception:
		await session.rollback()
		raise

	try:
		mail_sent = await notifications.send_verification_email(nickname, recipient, token)
	except Exception as exc:
		log.error("Повторная отправка подтверждения не завершена. Тип ошибки: %s", type(exc).__name__)
		raise MailDeliveryError() from None

	if not mail_sent:
		raise MailDeliveryError()

	return True