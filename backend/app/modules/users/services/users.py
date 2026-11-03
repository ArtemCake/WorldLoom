# backend/app/modules/users/services/users.py

"""Поиск пользователей и блокировка текущего аккаунта без фиксации транзакций."""

from hmac import compare_digest
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import lazyload
from backend.app.core.crypto import hash_email
from backend.app.modules.users.errors import ProfileSessionExpired
from backend.app.modules.users.models.user import User


async def get_user_by_id(session: AsyncSession, user_id: UUID | str, *, for_update: bool = False) -> User | None:
	"""Получить пользователя; при необходимости заблокировать строку."""
	identifier = UUID(str(user_id))
	statement = select(User).where(User.id == identifier).options(lazyload("*")).execution_options(populate_existing=True)

	if for_update:
		statement = statement.with_for_update()

	result = await session.execute(statement)
	return result.scalar_one_or_none()

async def get_user_by_email(session: AsyncSession, email: str, *, for_update: bool = False) -> User | None:
	"""Найти пользователя по поисковому HMAC адреса."""
	statement = select(User).where(User.email_hash == hash_email(email)).options(lazyload("*")).execution_options(populate_existing=True)

	if for_update:
		statement = statement.with_for_update()

	result = await session.execute(statement)
	return result.scalar_one_or_none()

async def lock_current_user(session: AsyncSession, user: User) -> User:
	"""Заблокировать аккаунт и проверить, что сессия запроса ещё действует."""
	user_id = user.id
	request_session_token = user.active_session_token

	if not isinstance(request_session_token, str) or not request_session_token:
		raise ProfileSessionExpired()

	current = await get_user_by_id(session, user_id, for_update=True)
	if current is None or not current.is_active:
		raise ProfileSessionExpired()

	active_token = current.active_session_token
	if not isinstance(active_token, str) or not active_token:
		raise ProfileSessionExpired()

	if not compare_digest(active_token.encode("utf-8"), request_session_token.encode("utf-8")):
		raise ProfileSessionExpired()

	return current