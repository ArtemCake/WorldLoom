# backend/app/modules/auth/services/mfa.py

"""Настройка TOTP, одноразовые резервные коды и завершение двухэтапного входа."""

from __future__ import annotations

import base64
import hashlib
import secrets
from uuid import UUID

import pyotp
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import lazyload

from backend.app.core.settings import WebAppSettings
from backend.app.modules.auth.errors import AuthError, InvalidCredentials, InvalidSession
from backend.app.modules.auth.models.mfa import MFADevice
from backend.app.modules.auth.services.authentication import issue_login_session
from backend.app.modules.auth.services.passwords import hash_password, verify_password
from backend.app.modules.auth.services.tokens import verify_token
from backend.app.modules.users.models.user import User
from backend.app.modules.users.services.users import get_user_by_id

TOTP_DEVICE_TYPE = "totp"
BACKUP_CODE_TYPE = "backup_code"
BACKUP_CODES_COUNT = 8

def _get_fernet(settings: WebAppSettings) -> Fernet:
	"""Сохранить алгоритм получения ключа старой реализации."""
	if not settings.SECRET_KEY:
		raise RuntimeError("Для MFA требуется SECRET_KEY")

	key = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
	return Fernet(base64.urlsafe_b64encode(key))

def _encrypt(value: str, settings: WebAppSettings) -> str:
	return _get_fernet(settings).encrypt(value.encode("utf-8")).decode("utf-8")

def _decrypt(token: str, settings: WebAppSettings) -> str:
	return _get_fernet(settings).decrypt(token.encode("utf-8")).decode("utf-8")

def _normalize_code(code: str) -> str:
	return code.strip().replace(" ", "")

async def _get_active_user_for_update(session: AsyncSession, user_id: UUID) -> User:
	user = await get_user_by_id(session, user_id, for_update=True)
	if user is None or not user.is_active:
		raise InvalidSession()
	return user

async def get_totp_device(session: AsyncSession, user_id: UUID) -> MFADevice | None:
	"""Прочитать TOTP-устройство без фиксации транзакции."""
	statement = select(MFADevice).where(MFADevice.user_id == user_id, MFADevice.type == TOTP_DEVICE_TYPE).options(lazyload("*"))
	result = await session.execute(statement)
	return result.scalar_one_or_none()

async def start_totp_setup(session: AsyncSession, user: User, *, settings: WebAppSettings) -> tuple[str, str]:
	"""Создать или заменить черновик TOTP только при выключенной MFA."""
	try:
		current_user = await _get_active_user_for_update(session, user.id)
		if current_user.is_2fa_enabled:
			raise AuthError("Двухфакторная аутентификация уже включена.")

		existing = await get_totp_device(session, current_user.id)
		if existing is not None:
			await session.delete(existing)
			await session.flush()

		secret = pyotp.random_base32()
		uri = pyotp.TOTP(secret).provisioning_uri(name=current_user.email, issuer_name=settings.PROJECT_NAME)
		device = MFADevice(
			user_id=current_user.id, type=TOTP_DEVICE_TYPE, secret=_encrypt(secret, settings), label="Приложение-аутентификатор",
		)
		session.add(device)
		await session.commit()
		return secret, uri
	except Exception:
		await session.rollback()
		raise

async def confirm_totp_setup(session: AsyncSession, user: User, code: str, *, settings: WebAppSettings) -> list[str] | None:
	"""Включить MFA и однократно вернуть открытые значения новых резервных кодов."""
	try:
		current_user = await _get_active_user_for_update(session, user.id)
		if current_user.is_2fa_enabled:
			raise AuthError("Двухфакторная аутентификация уже включена.")

		device = await get_totp_device(session, current_user.id)
		if device is None:
			await session.rollback()
			return None

		try:
			secret = _decrypt(device.secret, settings)
		except InvalidToken:
			await session.rollback()
			return None

		if not pyotp.TOTP(secret).verify(_normalize_code(code), valid_window=1):
			await session.rollback()
			return None

		await session.execute(delete(MFADevice).where(MFADevice.user_id == current_user.id, MFADevice.type == BACKUP_CODE_TYPE))

		backup_codes = [secrets.token_hex(4) for _ in range(BACKUP_CODES_COUNT)]
		for plain_code in backup_codes:
			session.add(MFADevice(user_id=current_user.id, type=BACKUP_CODE_TYPE, secret=hash_password(plain_code), is_backup=True))

		current_user.is_2fa_enabled = True
		await session.commit()
		return backup_codes
	except Exception:
		await session.rollback()
		raise

async def verify_login_code(session: AsyncSession, user: User, code: str, *, settings: WebAppSettings) -> bool:
	"""Проверить второй фактор без commit; вызывающий код обязан держать блокировку пользователя."""
	if not user.is_active or not user.is_2fa_enabled:
		return False

	normalized = _normalize_code(code)
	if not normalized:
		return False

	device = await get_totp_device(session, user.id)
	if device is not None:
		try:
			secret = _decrypt(device.secret, settings)
		except InvalidToken:
			pass
		else:
			if pyotp.TOTP(secret).verify(normalized, valid_window=1):
				return True

	statement = select(MFADevice).where(MFADevice.user_id == user.id, MFADevice.type == BACKUP_CODE_TYPE).options(lazyload("*"))
	result = await session.execute(statement)

	for backup in result.scalars().all():
		if verify_password(normalized, backup.secret):
			await session.delete(backup)
			await session.flush()
			return True

	return False

async def login_with_mfa(session: AsyncSession, mfa_token: str, code: str, *, settings: WebAppSettings) -> dict[str, str]:
	"""Атомарно проверить второй фактор, погасить резервный код и выдать сессию."""
	try:
		payload = verify_token(mfa_token, purpose="mfa_pending", settings=settings)
		if payload is None:
			raise InvalidSession("Сессия входа истекла, войдите заново.")

		user = await _get_active_user_for_update(session, UUID(payload["sub"]))
		if not user.is_2fa_enabled:
			raise InvalidSession("Сессия входа недействительна.")

		if not await verify_login_code(session, user, code, settings=settings):
			raise InvalidCredentials("Неверный код.")

		tokens = await issue_login_session(session, user, settings=settings)
		await session.commit()
		return tokens
	except Exception:
		await session.rollback()
		raise

async def disable_mfa(session: AsyncSession, user: User, password: str) -> None:
	"""Повторно проверить пароль и удалить все устройства MFA пользователя."""
	try:
		current_user = await _get_active_user_for_update(session, user.id)
		if not current_user.password_hash or not verify_password(password, current_user.password_hash):
			raise InvalidCredentials("Неверный пароль.")

		await session.execute(delete(MFADevice).where(MFADevice.user_id == current_user.id))
		current_user.is_2fa_enabled = False
		await session.commit()
	except Exception:
		await session.rollback()
		raise