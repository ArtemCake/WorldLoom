# backend/app/modules/games/services/lobby_service.py

"""Прикладные операции лобби без зависимости от HTTP.

Каждая операция ожидает сессию без посторонних ожидающих изменений.
Сервис выполняет flush, но не commit и не rollback.
Вызывающий слой отвечает за фиксацию, откат и закрытие сессии.

Блокировки удерживаются до завершения внешней транзакции.
При ошибке нельзя продолжать работу с той же транзакцией без отката.
"""

from __future__ import annotations
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import lazyload
from backend.app.modules.game_systems.models.game_systems import GameSystem
from backend.app.modules.games import errors
from backend.app.modules.games.models.lobby import Game, Invite, Party, Session as GameSession
from backend.app.modules.games.schemas.lobby import GameCreate, GameUpdate, InviteCreate, SessionCreate, SessionUpdate


DEFAULT_INVITE_LIFETIME = timedelta(minutes=10)

def _require_clean_session(session: AsyncSession) -> None:
	"""Не допускать неявного сохранения посторонних ORM-изменений."""
	if session.new or session.dirty or session.deleted:
		raise RuntimeError("Операция лобби требует сессии без ожидающих ORM-изменений")

async def _get_game(session: AsyncSession, game_id: UUID, *, lock: bool = False) -> Game:
	statement = (
		select(Game)
		.where(Game.id == game_id)
		.options(lazyload("*"))
		.execution_options(populate_existing=True)
	)

	if lock:
		statement = statement.with_for_update()

	game = (await session.execute(statement)).scalar_one_or_none()

	if game is None:
		raise errors.GameNotFound("Игра не найдена")

	return game

async def _require_master(session: AsyncSession, game_id: UUID, user_id: UUID) -> Game:
	game = await _get_game(session, game_id, lock=True)

	if game.master_id != user_id:
		raise errors.GameAccessDenied("Только мастер игры может это делать")

	return game

async def _get_party(session: AsyncSession, game_id: UUID, user_id: UUID, *, lock: bool = False) -> Party | None:
	statement = (
		select(Party)
		.where(Party.game_id == game_id, Party.user_id == user_id)
		.options(lazyload("*"))
		.execution_options(populate_existing=True)
	)

	if lock:
		statement = statement.with_for_update()

	return (await session.execute(statement)).scalar_one_or_none()

async def list_games_for_user(session: AsyncSession, user_id: UUID) -> list[Game]:
	_require_clean_session(session)
	active_membership = (
		select(Party.id)
		.where(
			Party.game_id == Game.id,
			Party.user_id == user_id,
			Party.is_active.is_(True),
			Party.role_in_game != "banned",
			)
		.exists()
	)
	statement = (
		select(Game)
		.where(or_(Game.master_id == user_id, active_membership))
		.options(lazyload("*"))
		.order_by(Game.created_at.desc(), Game.id)
		.execution_options(populate_existing=True)
	)
	result = await session.execute(statement)
	return list(result.scalars().all())

async def get_game(session: AsyncSession, game_id: UUID, user_id: UUID) -> Game:
	_require_clean_session(session)
	game = await _get_game(session, game_id)

	if game.master_id == user_id:
		return game

	membership = (
		select(Party.id)
		.where(
			Party.game_id == game_id,
			Party.user_id == user_id,
			Party.is_active.is_(True),
			Party.role_in_game != "banned",
			)
		.limit(1)
	)

	if (await session.execute(membership)).scalar_one_or_none() is None:
		raise errors.GameAccessDenied("Нет доступа к этой игре")

	return game

async def get_session_for_user(session: AsyncSession, session_id: UUID, user_id: UUID, *, require_active: bool = False) -> GameSession:
	_require_clean_session(session)
	statement = (
		select(GameSession)
		.where(GameSession.id == session_id)
		.options(lazyload("*"))
		.execution_options(populate_existing=True)
	)
	game_session = (await session.execute(statement)).scalar_one_or_none()

	if game_session is None:
		raise errors.GameSessionNotFound("Сессия не найдена")

	await get_game(session, game_session.game_id, user_id)

	if require_active and not game_session.is_active:
		raise errors.GameStateConflict("Игровая сессия завершена")

	return game_session

async def list_party(session: AsyncSession, game_id: UUID, user_id: UUID) -> list[Party]:
	await get_game(session, game_id, user_id)
	statement = (
		select(Party)
		.where(Party.game_id == game_id)
		.options(lazyload("*"))
		.execution_options(populate_existing=True)
	)
	result = await session.execute(statement)
	return list(result.scalars().all())

async def create_game(session: AsyncSession, master_id: UUID, data: GameCreate) -> Game:
	_require_clean_session(session)
	systems = GameSystem.__table__
	statement = (
		select(systems.c.id, systems.c.is_active)
		.where(systems.c.id == data.system_id)
		.with_for_update()
	)
	system = (await session.execute(statement)).mappings().one_or_none()

	if system is None:
		raise errors.GameSystemNotFound("Игровая система не найдена")

	if not system["is_active"]:
		raise errors.GameStateConflict("Игровая система деактивирована. Создание новых игр недоступно.")

	game = Game(master_id=master_id, status="draft", **data.model_dump())
	session.add(game)
	await session.flush()
	session.add(Party(game_id=game.id, user_id=master_id, role_in_game="assistant_dm", is_active=True))
	await session.flush()
	return game

async def update_game(session: AsyncSession, game_id: UUID, master_id: UUID, data: GameUpdate) -> Game:
	_require_clean_session(session)
	game = await _require_master(session, game_id, master_id)

	for name, value in data.model_dump(exclude_unset=True).items():
		setattr(game, name, value)

	await session.flush()
	return game

async def archive_game(session: AsyncSession, game_id: UUID, master_id: UUID) -> None:
	_require_clean_session(session)
	game = await _require_master(session, game_id, master_id)
	game.status = "archived"
	await session.flush()

async def update_party_role(session: AsyncSession, game_id: UUID, target_user_id: UUID, master_id: UUID, role_in_game: str) -> Party:
	_require_clean_session(session)

	if role_in_game not in ("player", "assistant_dm", "banned"):
		raise errors.InvalidGameInput("Недопустимая роль участника")

	await _require_master(session, game_id, master_id)
	party = await _get_party(session, game_id, target_user_id, lock=True)

	if party is None:
		raise errors.PartyMemberNotFound("Участник не найден в этой игре")

	party.role_in_game = role_in_game
	await session.flush()
	return party

async def leave_game(session: AsyncSession, game_id: UUID, user_id: UUID) -> None:
	_require_clean_session(session)
	await _get_game(session, game_id, lock=True)
	party = await _get_party(session, game_id, user_id, lock=True)

	if party is None:
		raise errors.PartyMemberNotFound("Вы не состоите в этой игре")

	party.is_active = False
	await session.flush()

async def create_invite(session: AsyncSession, game_id: UUID, master_id: UUID, data: InviteCreate) -> Invite:
	_require_clean_session(session)
	await _require_master(session, game_id, master_id)
	now = datetime.now(timezone.utc)
	expires_at = data.expires_at if data.expires_at is not None else now + DEFAULT_INVITE_LIFETIME

	if expires_at <= now:
		raise errors.InvalidGameInput("Срок действия приглашения должен быть в будущем")

	invite = Invite(
		token=secrets.token_urlsafe(24),
		game_id=game_id,
		creator_id=master_id,
		expires_at=expires_at,
		uses_limit=data.uses_limit if data.uses_limit is not None else 1,
		uses_current=0,
		message=data.message,
	)
	session.add(invite)
	await session.flush()
	return invite

async def claim_invite(session: AsyncSession, token: str, user_id: UUID) -> Party:
	_require_clean_session(session)
	game_id = (await session.execute(select(Invite.game_id).where(Invite.token == token))).scalar_one_or_none()

	if game_id is None:
		raise errors.InviteNotFound("Приглашение не найдено")

	await _get_game(session, game_id, lock=True)
	statement = (
		select(Invite)
		.where(Invite.token == token)
		.options(lazyload("*"))
		.with_for_update()
		.execution_options(populate_existing=True)
	)
	invite = (await session.execute(statement)).scalar_one_or_none()

	if invite is None:
		raise errors.InviteNotFound("Приглашение не найдено")

	if invite.game_id != game_id:
		raise errors.GameStateConflict("Игра приглашения изменилась")

	now = datetime.now(timezone.utc)

	if invite.expires_at <= now or invite.uses_current >= invite.uses_limit:
		raise errors.InviteExpired("Приглашение больше не действует")

	party = await _get_party(session, game_id, user_id, lock=True)

	if party is not None and party.role_in_game == "banned":
		raise errors.GameAccessDenied("Доступ к этой игре заблокирован")

	if party is None:
		party = Party(game_id=game_id, user_id=user_id, role_in_game="player", is_active=True)
		session.add(party)
	else:
		party.is_active = True

	invite.uses_current += 1
	invite.claimed_by = user_id
	await session.flush()
	return party

async def is_game_master(session: AsyncSession, game_id: UUID, user_id: UUID) -> bool:
	_require_clean_session(session)
	statement = select(Game.master_id).where(Game.id == game_id)
	master_id = (await session.execute(statement)).scalar_one_or_none()
	return master_id is not None and master_id == user_id

async def start_session(session: AsyncSession, game_id: UUID, master_id: UUID, data: SessionCreate) -> GameSession:
	_require_clean_session(session)
	await _require_master(session, game_id, master_id)
	statement = select(GameSession.id).where(GameSession.game_id == game_id, GameSession.is_active.is_(True)).limit(1)

	if (await session.execute(statement)).scalar_one_or_none() is not None:
		raise errors.GameStateConflict("В этой игре уже есть активная сессия")

	game_session = GameSession(game_id=game_id, is_active=True, **data.model_dump())
	session.add(game_session)
	await session.flush()
	return game_session

async def list_sessions(session: AsyncSession, game_id: UUID, user_id: UUID) -> list[GameSession]:
	await get_game(session, game_id, user_id)
	statement = (
		select(GameSession)
		.where(GameSession.game_id == game_id)
		.options(lazyload("*"))
		.order_by(GameSession.start_time.desc(), GameSession.id)
		.execution_options(populate_existing=True)
	)
	result = await session.execute(statement)
	return list(result.scalars().all())

async def get_active_session(session: AsyncSession, game_id: UUID, user_id: UUID) -> GameSession:
	await get_game(session, game_id, user_id)
	statement = (
		select(GameSession)
		.where(GameSession.game_id == game_id, GameSession.is_active.is_(True))
		.options(lazyload("*"))
		.execution_options(populate_existing=True)
	)
	game_session = (await session.execute(statement)).scalar_one_or_none()

	if game_session is None:
		raise errors.GameSessionNotFound("Активная сессия не найдена")

	return game_session

async def _get_owned_session(session: AsyncSession, session_id: UUID, master_id: UUID) -> GameSession:
	game_id = (await session.execute(select(GameSession.game_id).where(GameSession.id == session_id))).scalar_one_or_none()

	if game_id is None:
		raise errors.GameSessionNotFound("Сессия не найдена")

	await _require_master(session, game_id, master_id)
	statement = (
		select(GameSession)
		.where(GameSession.id == session_id)
		.options(lazyload("*"))
		.with_for_update()
		.execution_options(populate_existing=True)
	)
	game_session = (await session.execute(statement)).scalar_one_or_none()

	if game_session is None:
		raise errors.GameSessionNotFound("Сессия не найдена")

	if game_session.game_id != game_id:
		raise errors.GameStateConflict("Игра сессии изменилась")

	return game_session

async def update_session(session: AsyncSession, session_id: UUID, master_id: UUID, data: SessionUpdate) -> GameSession:
	_require_clean_session(session)
	game_session = await _get_owned_session(session, session_id, master_id)

	for name, value in data.model_dump(exclude_unset=True).items():
		setattr(game_session, name, value)

	await session.flush()
	return game_session

async def end_session(session: AsyncSession, session_id: UUID, master_id: UUID) -> GameSession:
	_require_clean_session(session)
	game_session = await _get_owned_session(session, session_id, master_id)

	if game_session.is_active:
		game_session.is_active = False
		game_session.end_time = datetime.now(timezone.utc)
		await session.flush()

	return game_session