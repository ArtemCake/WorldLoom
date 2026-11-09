# backend/app/modules/users/services/profile.py

"""Изменение ролей, оформления и пароля текущего пользователя."""

import asyncio
from datetime import datetime, timezone
from dataclasses import dataclass
from uuid import uuid4, UUID
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.modules.auth.schemas import validate_password_complexity
from backend.app.modules.auth.services.passwords import hash_password, verify_password
from backend.app.modules.users.enums import SystemRole
from backend.app.modules.users.errors import CurrentPasswordInvalid, ProfileError
from backend.app.modules.users.models.user import User
from backend.app.modules.users.permissions import get_self_editable_roles
from backend.app.modules.users.schemas import UpdateThemeDTO
from backend.app.modules.users.services.users import lock_current_user
from pydantic import EmailStr, TypeAdapter, ValidationError
from backend.app.core.crypto import hash_email
from backend.app.core.logging import get_logger
from backend.app.core.settings import WebAppSettings
from backend.app.modules.auth.services.email_verification import EMAIL_VERIFICATION_VERSION_KEY, build_email_verification_token
from backend.app.modules.auth.services.notifications import AuthNotifications
from backend.app.modules.users.errors import ProfileConflict
from backend.app.modules.users.services.avatars import remove_owned_avatar, save_avatar


log = get_logger(__name__)
_email_validator = TypeAdapter(EmailStr)

async def _lock_current_user(session: AsyncSession, user: User) -> User:
	"""Использовать общую блокировку и повторную проверку сессии."""
	return await lock_current_user(session, user)

async def update_own_roles(session: AsyncSession, user: User, requested_roles: list[SystemRole]) -> list[SystemRole]:
	"""Изменить только доступные пользователю роли, сохранив защищённые."""
	try:
		current = await _lock_current_user(session, user)
		scope = set(get_self_editable_roles(current.roles))
		protected = [role for role in (current.roles or []) if role not in scope]
		chosen = [SystemRole(role) for role in requested_roles if role in scope]
		final_roles = list(dict.fromkeys(protected + chosen))

		if not final_roles:
			raise ProfileError("У пользователя должна остаться хотя бы одна роль")

		current.roles = final_roles
		current.updated_at = datetime.now(timezone.utc)
		await session.commit()
		return final_roles
	except Exception:
		await session.rollback()
		raise

async def update_theme(session: AsyncSession, user: User, payload: UpdateThemeDTO) -> str:
	"""Обновить оформление, не затирая остальные настройки и согласие с условиями."""
	try:
		current = await _lock_current_user(session, user)
		profile_settings = dict(current.profile_settings or {})
		profile_settings["theme"] = payload.theme

		if payload.theme_color is not None:
			profile_settings["theme_color"] = payload.theme_color

		current.profile_settings = profile_settings
		current.updated_at = datetime.now(timezone.utc)
		await session.commit()
		return payload.theme
	except Exception:
		await session.rollback()
		raise

async def change_password(session: AsyncSession, user: User, old_password: str, new_password: str) -> None:
	"""Повторно проверить пароль, сохранить новый хеш и завершить активную сессию."""
	try:
		current = await _lock_current_user(session, user)
		if not current.password_hash or not verify_password(old_password, current.password_hash):
			raise CurrentPasswordInvalid()

		if not 8 <= len(new_password) <= 128:
			raise ProfileError("Пароль должен быть от 8 до 128 символов.")

		complexity_error = validate_password_complexity(new_password)
		if complexity_error:
			raise ProfileError(complexity_error)

		current.password_hash = hash_password(new_password)
		current.active_session_token = None
		current.updated_at = datetime.now(timezone.utc)
		await session.commit()
	except Exception:
		await session.rollback()
		raise

@dataclass(frozen=True)
class ProfileUpdateResult:
	avatar_url: str | None
	email_changed: bool
	mail_sent: bool | None

async def _find_profile_conflict(session: AsyncSession, user_id: UUID, nickname: str, email_hash: str) -> str | None:
	email_owner = await session.scalar(select(User.id).where(User.email_hash == email_hash, User.id != user_id))
	if email_owner is not None:
		return "Пользователь с таким адресом электронной почты уже существует."

	nickname_owner = await session.scalar(select(User.id).where(User.nickname == nickname, User.id != user_id))
	if nickname_owner is not None:
		return "Этот никнейм уже занят."

	return None

async def update_user_profile(session: AsyncSession, user: User, nickname: str, email: str, avatar_content: bytes | None = None, *,
		settings: WebAppSettings, notifications: AuthNotifications) -> ProfileUpdateResult:
	"""Сохранить профиль; письмо отправить и старый управляемый аватар убрать после commit."""
	user_id = user.id
	new_avatar_url: str | None = None
	commit_started = False

	try:
		if not isinstance(nickname, str) or not nickname.strip() or len(nickname) > 50:
			raise ProfileError("Никнейм должен содержать от 1 до 50 символов и не состоять только из пробелов.")

		try:
			email = str(_email_validator.validate_python(email))
		except ValidationError:
			raise ProfileError("Укажите корректный адрес электронной почты.") from None

		requested_email_hash = hash_email(email)
		current = await _lock_current_user(session, user)
		conflict = await _find_profile_conflict(session, user_id, nickname, requested_email_hash)
		if conflict is not None:
			raise ProfileConflict(conflict)

		old_avatar_url = current.avatar_url
		email_changed = current.email != email
		changed = current.nickname != nickname or email_changed or avatar_content is not None

		current.nickname = nickname
		if email_changed:
			current.email = email
			current.is_email_verified = False
			profile_settings = dict(current.profile_settings or {})
			profile_settings[EMAIL_VERIFICATION_VERSION_KEY] = uuid4().hex
			current.profile_settings = profile_settings

		if avatar_content is not None:
			new_avatar_url = await asyncio.to_thread(save_avatar,nickname,  user_id, avatar_content)
			current.avatar_url = new_avatar_url

		if changed:
			current.updated_at = datetime.now(timezone.utc)

		recipient = current.email
		recipient_name = current.nickname
		avatar_url = current.avatar_url
		verification_token = build_email_verification_token(current, settings=settings) if email_changed else None

		await session.flush()
		commit_started = True
		await session.commit()
	except IntegrityError:
		await session.rollback()
		if not commit_started and new_avatar_url is not None:
			await asyncio.to_thread(remove_owned_avatar, new_avatar_url, user_id)

		try:
			conflict = await _find_profile_conflict(session, user_id, nickname, requested_email_hash)
		finally:
			await session.rollback()

		if conflict is not None:
			raise ProfileConflict(conflict) from None
		raise
	except Exception:
		await session.rollback()
		if not commit_started and new_avatar_url is not None:
			await asyncio.to_thread(remove_owned_avatar, new_avatar_url, user_id)
		raise

	# Старый адрес мог содержать прежний никнейм: владелец проверяется по идентификатору из каталога.
	if new_avatar_url is not None and old_avatar_url != new_avatar_url:
		await asyncio.to_thread(remove_owned_avatar, old_avatar_url, user_id)

	mail_sent: bool | None = None
	if verification_token is not None:
		try:
			mail_sent = await notifications.send_verification_email(recipient_name, recipient, verification_token)
		except Exception as exc:
			log.error("Профиль сохранён, отправка подтверждения не завершена. Тип ошибки: %s", type(exc).__name__)
			mail_sent = False

	return ProfileUpdateResult(avatar_url=avatar_url, email_changed=email_changed, mail_sent=mail_sent)