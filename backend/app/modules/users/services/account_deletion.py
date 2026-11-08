# backend/app/modules/users/services/account_deletion.py

"""Деактивация и удаление аккаунта с фиксацией изменений одной транзакцией."""

import asyncio
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.logging import get_logger
from backend.app.modules.auth.services.passwords import verify_password
from backend.app.modules.users.errors import AccountDeletionConflict, CurrentPasswordInvalid, LocalPasswordRequired
from backend.app.modules.users.models.user import User
from backend.app.modules.users.services.avatars import remove_owned_avatar
from backend.app.modules.users.services.users import get_user_by_id, lock_current_user


log = get_logger(__name__)

async def _commit_account_deletion(session: AsyncSession, user: User, *, permanent: bool) -> None:
	"""Применить удаление; очистку управляемого аватара выполнять только после commit."""
	user_id = user.id
	avatar_url = user.avatar_url

	try:
		user.active_session_token = None

		if permanent:
			# Сохранить ORM-каскады старой реализации, а не обходить их прямым DELETE.
			await session.delete(user)
		else:
			now = datetime.now(timezone.utc)
			user.is_active = False
			user.deleted_at = now
			user.updated_at = now

		await session.commit()
	except IntegrityError:
		await session.rollback()
		raise AccountDeletionConflict() from None
	except Exception:
		await session.rollback()
		raise

	if permanent:
		try:
			await asyncio.to_thread(remove_owned_avatar, avatar_url, user.nickname, user_id)
		except Exception as exc:
			# Удаление БД уже подтверждено: сбой очистки файла не должен выглядеть как его откат.
			log.error("Аккаунт удалён, очистка аватара не завершена. Тип ошибки: %s", type(exc).__name__)

async def delete_current_account(session: AsyncSession, user: User, password: str, *, permanent: bool = False) -> None:
	"""Повторно проверить текущую сессию и пароль перед самостоятельным удалением."""
	try:
		current = await lock_current_user(session, user)

		if not current.password_hash:
			raise LocalPasswordRequired()

		if not verify_password(password, current.password_hash):
			raise CurrentPasswordInvalid("Неверный пароль.")

		await _commit_account_deletion(session, current, permanent=permanent)
	except Exception:
		await session.rollback()
		raise

async def soft_delete_user(session: AsyncSession, user_id: UUID | str) -> bool:
	"""Внутренняя операция деактивации; права администратора проверяет вызывающий слой."""
	try:
		user = await get_user_by_id(session, user_id, for_update=True)
		if user is None or not user.is_active:
			await session.rollback()
			return False

		await _commit_account_deletion(session, user, permanent=False)
		return True
	except Exception:
		await session.rollback()
		raise

async def hard_delete_user(session: AsyncSession, user_id: UUID | str) -> None:
	"""Внутренняя операция удаления; права администратора проверяет вызывающий слой."""
	try:
		user = await get_user_by_id(session, user_id, for_update=True)
		if user is None:
			await session.rollback()
			return

		await _commit_account_deletion(session, user, permanent=True)
	except Exception:
		await session.rollback()
		raise