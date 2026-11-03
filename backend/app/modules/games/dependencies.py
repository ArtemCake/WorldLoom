# backend/app/modules/games/dependencies.py

"""HTTP-зависимости игр и общая граница изменяющих операций."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.bootstrap import AppResources
from backend.app.modules.auth.dependencies import get_current_user
from backend.app.modules.games import errors
from backend.app.modules.users.models.user import User
from backend.app.web.csrf import enforce_csrf


log = logging.getLogger(__name__)
WRITE_DEPENDENCIES = [Depends(enforce_csrf)]


def get_resources(request: Request) -> AppResources:
	resources = getattr(request.app.state, "resources", None)

	if not isinstance(resources, AppResources):
		raise RuntimeError("Ресурсы приложения не подключены")

	return resources

async def get_actor_id(user: User = Depends(get_current_user)) -> UUID:
	return user.id

async def operation_session(request: Request) -> AsyncIterator[AsyncSession]:
	async with get_resources(request).database.session() as session:
		yield session

async def write_operation(session: AsyncSession, operation: Awaitable[Any], serialize: Callable[[Any], Any] = lambda value: value) -> Any:
	"""Проверить результат до commit и дождаться завершения запущенной фиксации."""
	try:
		result = serialize(await operation)
	except BaseException:
		try:
			await session.rollback()
		except Exception:
			log.exception("Не удалось откатить операцию игры")
		raise

	task = asyncio.create_task(session.commit())
	cancelled = False

	while True:
		try:
			await asyncio.shield(task)
			break
		except asyncio.CancelledError:
			if task.cancelled():
				raise

			cancelled = True
		except Exception as error:
			log.error("Результат фиксации операции игры не подтверждён. Тип ошибки: %s", type(error).__name__)
			raise errors.GameCommitOutcomeUnknown("Результат сохранения не подтверждён") from error

	if cancelled:
		raise asyncio.CancelledError()

	return result


ActorId = Annotated[UUID, Depends(get_actor_id)]
OperationSession = Annotated[AsyncSession, Depends(operation_session)]