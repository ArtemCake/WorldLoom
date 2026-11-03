# backend/app/modules/games/services/game_state_access.py

"""Общий доступ к игровому столу и порядок блокировок.

Не выполняет commit, rollback или изменение моделей.
После ошибки вызывающий слой завершает транзакцию откатом.
"""

from __future__ import annotations
from dataclasses import dataclass
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import lazyload
from backend.app.modules.games import errors
from backend.app.modules.games.models.lobby import Game, Party, Session as GameSession


@dataclass(frozen=True)
class GameStateContext:
	game: Game
	game_session: GameSession
	is_master: bool

def require_clean_session(session: AsyncSession) -> None:
	if session.new or session.dirty or session.deleted:
		raise RuntimeError("Операция игрового стола требует сессии без ожидающих ORM-изменений")

async def get_session_context(session: AsyncSession, session_id: UUID, actor_id: UUID, *, write: bool = False, master_only: bool = False,
        require_active: bool = False) -> GameStateContext:
	require_clean_session(session)
	game_id = (await session.execute(select(GameSession.game_id).where(GameSession.id == session_id))).scalar_one_or_none()

	if game_id is None:
		raise errors.GameSessionNotFound("Игровая сессия не найдена")

	game_statement = (
		select(Game)
		.where(Game.id == game_id)
		.options(lazyload("*"))
		.execution_options(populate_existing=True)
	)

	if write:
		game_statement = game_statement.with_for_update()

	game = (await session.execute(game_statement)).scalar_one_or_none()

	if game is None:
		raise errors.GameNotFound("Игра не найдена")

	is_master = game.master_id == actor_id

	if master_only and not is_master:
		raise errors.GameAccessDenied("Для операции нужны права мастера игры")

	if not is_master:
		membership = (
			select(Party.id)
			.where(
				Party.game_id == game_id,
				Party.user_id == actor_id,
				Party.is_active.is_(True),
				Party.role_in_game != "banned",
				)
			.limit(1)
		)

		if (await session.execute(membership)).scalar_one_or_none() is None:
			raise errors.GameAccessDenied("Нет доступа к этой игре")

	session_statement = (
		select(GameSession)
		.where(GameSession.id == session_id)
		.options(lazyload("*"))
		.execution_options(populate_existing=True)
	)

	if write:
		session_statement = session_statement.with_for_update()

	game_session = (await session.execute(session_statement)).scalar_one_or_none()

	if game_session is None:
		raise errors.GameSessionNotFound("Игровая сессия не найдена")

	if game_session.game_id != game_id:
		raise errors.GameStateConflict("Принадлежность игровой сессии изменилась")

	if require_active and not game_session.is_active:
		raise errors.GameStateConflict("Игровая сессия завершена")

	return GameStateContext(game=game, game_session=game_session, is_master=is_master)