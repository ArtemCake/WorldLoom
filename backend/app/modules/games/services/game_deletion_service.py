# backend/app/modules/games/services/game_deletion_service.py

"""Подготовка удаления игры и чтение задания очистки.

Модуль не выполняет commit, rollback или удаление файлов.
Транзакцией управляет вызывающий слой.

stage_game_deletion возвращает True, если удаление подготовлено,
и False, если игра уже отсутствует. True не означает, что
транзакция зафиксирована или файлы очищены.

Идентификатор пользователя поступает из проверенной аутентификации.
Административный исполнитель отдельно проверяет свои полномочия
и передаёт фактического владельца игры.

Проверка общих каталогов сохраняет исходную проверку путей карт.
Она не является полной блокировкой файлового хранилища.
"""

from __future__ import annotations
from collections.abc import Awaitable, Callable
from copy import deepcopy
from pathlib import Path
from typing import Any
from uuid import UUID
from sqlalchemy import delete, insert, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.modules.games.errors import GameCleanupJobNotFound, GameDeletionConflict, GameDeletionForbidden, InvalidGameDeletion
from backend.app.modules.games.models.lobby import DiceRoll, Game, GameDeletionJob, Party, Session as GameSession
from backend.app.modules.maps.models import CampaignMap
from backend.app.modules.maps.services import map_cleanup_service
from backend.app.modules.users.models.user import User


_GAMES = Game.__table__
_PARTIES = Party.__table__
_SESSIONS = GameSession.__table__
_ROLLS = DiceRoll.__table__
_JOBS = GameDeletionJob.__table__
_MAPS = CampaignMap.__table__
_USERS = User.__table__

def _prepare(session: AsyncSession, game_id: UUID, master_id: UUID) -> None:
	if not isinstance(game_id, UUID) or not isinstance(master_id, UUID):
		raise InvalidGameDeletion("Требуются идентификаторы игры и проверенного пользователя")

	if session.new or session.dirty or session.deleted:
		raise RuntimeError("Операция требует сессии без ожидающих ORM-изменений")

async def _require_deletion_transaction(session: AsyncSession) -> None:
	if session.get_bind().dialect.name != "postgresql":
		raise GameDeletionConflict("Подготовка удаления игры рассчитана на PostgreSQL")

	result = await session.execute(text("SHOW transaction_isolation"))

	if result.scalar_one().lower() != "read committed":
		raise GameDeletionConflict("Для подготовки удаления игры требуется уровень изоляции READ COMMITTED")

def _validate_cleanup_plan(plan: dict[str, Any], game_id: UUID, master_id: UUID, *, root: Path) -> None:
	try:
		map_cleanup_service.validate_plan(plan, root=root)

		if plan["game_id"] != str(game_id) or plan["master_id"] != str(master_id):
			raise ValueError("План относится к другой игре или другому владельцу")

	except (OSError, ValueError, RuntimeError) as exc:
		raise GameDeletionConflict("Не удалось безопасно проверить план очистки карт") from exc

async def _assert_unshared_directories(session: AsyncSession, game_id: UUID, directories: list[str]) -> None:
	for relative in directories:
		result = await session.execute(
			select(_MAPS.c.id)
			.where(
				_MAPS.c.game_id != game_id,
				_MAPS.c.background_storage_path.startswith(f"{relative}/", autoescape=True),
				)
			.limit(1)
		)

		if result.scalar_one_or_none() is not None:
			raise GameDeletionConflict("Каталог используется картами другой игры. Удаление остановлено")

async def stage_game_deletion(session: AsyncSession, game_id: UUID, master_id: UUID, *, root: Path) -> bool:
	"""Подготовить удаление без фиксации транзакции и очистки файлов."""
	_prepare(session, game_id, master_id)
	await _require_deletion_transaction(session)

	result = await session.execute(
		select(_GAMES.c.id, _GAMES.c.master_id, _GAMES.c.maps_storage_folder)
		.where(_GAMES.c.id == game_id)
		.with_for_update()
	)
	game = result.mappings().one_or_none()

	if game is None:
		return False

	if game["master_id"] is None:
		raise GameDeletionConflict("У игры отсутствует владелец. Требуется проверка каталогов хранения")

	if game["master_id"] != master_id:
		raise GameDeletionForbidden("Только мастер игры может подготовить её удаление")

	result = await session.execute(select(_JOBS.c.game_id).where(_JOBS.c.game_id == game_id))

	if result.scalar_one_or_none() is not None:
		raise GameDeletionConflict("Для существующей игры уже сохранено задание удаления. Требуется проверка состояния")

	result = await session.execute(
		select(_MAPS.c.id, _MAPS.c.background_storage_path)
		.where(_MAPS.c.game_id == game_id)
		.order_by(_MAPS.c.id)
		.with_for_update()
	)
	maps = result.all()

	result = await session.execute(select(_USERS.c.maps_storage_folder).where(_USERS.c.id == master_id))
	master_folder = result.scalar_one_or_none()

	try:
		plan = map_cleanup_service.build_plan(
			game_id, master_id, master_folder, game["maps_storage_folder"], maps, root=root
		)
	except (OSError, ValueError, RuntimeError) as exc:
		raise GameDeletionConflict("Не удалось безопасно определить каталог карт. Удаление не подготовлено") from exc

	await _assert_unshared_directories(session, game_id, plan["directories"])

	await session.execute(
		insert(_JOBS).values(
			game_id=game_id,
			master_id=master_id,
			cleanup_plan=plan,
			cleanup_complete=False,
		)
	)

	session_ids = select(_SESSIONS.c.id).where(_SESSIONS.c.game_id == game_id)
	party_ids = select(_PARTIES.c.id).where(_PARTIES.c.game_id == game_id)

	await session.execute(
		delete(_ROLLS).where(
			or_(
				_ROLLS.c.session_id.in_(session_ids),
				_ROLLS.c.party_id.in_(party_ids),
			)
		)
	)
	result = await session.execute(
		delete(_GAMES)
		.where(_GAMES.c.id == game_id)
		.returning(_GAMES.c.id)
	)

	if result.scalar_one_or_none() != game_id:
		raise GameDeletionConflict("Удаление игры не подтверждено. Требуется откат транзакции")

	return True

async def get_cleanup_job(session: AsyncSession, game_id: UUID, master_id: UUID, *, root: Path) -> dict[str, Any]:
	"""Прочитать задание владельца без запуска очистки и блокировки задания."""
	_prepare(session, game_id, master_id)

	result = await session.execute(
		select(_JOBS.c.game_id, _JOBS.c.master_id, _JOBS.c.cleanup_plan, _JOBS.c.cleanup_complete)
		.where(_JOBS.c.game_id == game_id)
	)
	job = result.mappings().one_or_none()

	if job is None:
		raise GameCleanupJobNotFound("Задание очистки игры не найдено")

	if job["master_id"] != master_id:
		raise GameDeletionForbidden("Задание очистки доступно только владельцу удалённой игры")

	if not isinstance(job["cleanup_complete"], bool):
		raise GameDeletionConflict("Состояние задания очистки имеет неподдерживаемый формат")

	plan = deepcopy(job["cleanup_plan"])
	_validate_cleanup_plan(plan, game_id, master_id, root=root)

	return {
		"game_id": game_id,
		"master_id": master_id,
		"cleanup_plan": plan,
		"cleanup_complete": job["cleanup_complete"],
	}

async def finish_cleanup(session: AsyncSession, game_id: UUID, master_id: UUID, executor: Callable[[dict[str, Any], Path], Awaitable[None]], *, root: Path) -> None:
	"""Выполнить очистку и подготовить отметку завершения без commit.

	Вызов разрешён только в отдельной транзакции после фиксации
	удаления игры. Блокировка задания удерживается до завершения
	executor и транзакции вызывающего слоя.

	executor обязан дождаться окончания файловых операций,
	включая случай отмены асинхронной задачи.
	"""
	_prepare(session, game_id, master_id)
	await _require_deletion_transaction(session)

	result = await session.execute(
		select(_JOBS.c.game_id, _JOBS.c.master_id, _JOBS.c.cleanup_plan, _JOBS.c.cleanup_complete)
		.where(_JOBS.c.game_id == game_id)
		.with_for_update()
	)
	job = result.mappings().one_or_none()

	if job is None:
		raise GameCleanupJobNotFound("Задание очистки игры не найдено")

	if job["master_id"] != master_id:
		raise GameDeletionForbidden("Очистка доступна только владельцу удалённой игры")

	if not isinstance(job["cleanup_complete"], bool):
		raise GameDeletionConflict("Состояние задания очистки имеет неподдерживаемый формат")

	result = await session.execute(select(_GAMES.c.id).where(_GAMES.c.id == game_id))

	if result.scalar_one_or_none() is not None:
		raise GameDeletionConflict("Игра ещё существует. Выполнение файловой очистки запрещено")

	if job["cleanup_complete"]:
		return

	plan = deepcopy(job["cleanup_plan"])
	_validate_cleanup_plan(plan, game_id, master_id, root=root)

	await executor(plan, root)

	result = await session.execute(
		update(_JOBS)
		.where(
			_JOBS.c.game_id == game_id,
			_JOBS.c.master_id == master_id,
			_JOBS.c.cleanup_complete.is_(False),
			)
		.values(cleanup_complete=True)
		.returning(_JOBS.c.game_id)
	)

	if result.scalar_one_or_none() != game_id:
		raise GameDeletionConflict("Не удалось подтвердить завершение задания очистки")