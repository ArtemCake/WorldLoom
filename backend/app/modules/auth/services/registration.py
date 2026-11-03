# backend/app/modules/auth/services/registration.py

"""Создание аккаунта и отправка письма после фиксации регистрации."""

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.logging import get_logger
from backend.app.core.settings import WebAppSettings
from backend.app.modules.auth.errors import RegistrationConflict
from backend.app.modules.auth.schemas import RegisterRequest
from backend.app.modules.auth.services.notifications import AuthNotifications
from backend.app.modules.auth.services.passwords import hash_password
from backend.app.modules.auth.services.email_verification import build_email_verification_token
from backend.app.modules.users.enums import SystemRole
from backend.app.modules.users.models.user import User
from backend.app.core.crypto import hash_email

log = get_logger(__name__)

@dataclass(frozen=True)
class RegistrationResult:
	user_id: UUID
	mail_sent: bool

async def _find_registration_conflict(session: AsyncSession, email: str, nickname: str) -> str | None:
	"""Проверить занятость без загрузки связей пользователя."""
	email_id = await session.scalar(select(User.id).where(User.email_hash == hash_email(email)))
	if email_id is not None:
		return "Пользователь с таким email уже существует"

	nickname_id = await session.scalar(select(User.id).where(User.nickname == nickname))
	if nickname_id is not None:
		return "Этот никнейм уже занят."

	return None

async def register_user(
		session: AsyncSession, data: RegisterRequest, *, settings: WebAppSettings, notifications: AuthNotifications,
) -> RegistrationResult:
	"""Атомарно сохранить аккаунт и согласие с условиями; SMTP выполнять после commit."""
	data = RegisterRequest.model_validate(data.model_dump())
	email = str(data.email)

	try:
		conflict = await _find_registration_conflict(session, email, data.nickname)
		if conflict is not None:
			raise RegistrationConflict(conflict)

		user_id = uuid4()
		user = User(
			id=user_id, email=email, nickname=data.nickname, password_hash=hash_password(data.password), roles=[SystemRole.PLAYER],
			is_active=True, is_email_verified=False, is_2fa_enabled=False,
			profile_settings={"terms_accepted_at": datetime.now(timezone.utc).isoformat(), "terms_version": "1.0"},
		)
		session.add(user)

		# Проверить ограничения БД и подготовить токен до фиксации аккаунта.
		await session.flush()
		verification_token = build_email_verification_token(user, settings=settings)
		await session.commit()
	except IntegrityError:
		await session.rollback()

		# Параллельный запрос мог занять email или никнейм после предварительной проверки.
		try:
			conflict = await _find_registration_conflict(session, email, data.nickname)
		finally:
			await session.rollback()

		if conflict is not None:
			raise RegistrationConflict(conflict) from None

		# Другие нарушения целостности нельзя выдавать за занятый email.
		raise
	except Exception:
		await session.rollback()
		raise

	try:
		mail_sent = await notifications.send_verification_email(data.nickname, email, verification_token)
	except Exception as exc:
		log.error("Регистрация сохранена, отправка подтверждения не завершена. Тип ошибки: %s", type(exc).__name__)
		mail_sent = False

	return RegistrationResult(user_id=user_id, mail_sent=mail_sent)