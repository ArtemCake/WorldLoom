# backend/app/modules/games/services/token_service.py

"""Токены игрового стола без HTTP и встроенных правил игровой системы.

Сервис сохраняет переданные значения и проверяет доступ и связи.
Не рассчитывает стоимость движения, характеристики или эффекты.
Выполняет flush, но не commit и не rollback.
"""

from __future__ import annotations
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import lazyload
from backend.app.modules.catalog.models.worldbuilding import NPC
from backend.app.modules.characters.models import CharacterSheet
from backend.app.modules.games import errors
from backend.app.modules.games.schemas.game_state import TokenCreate, TokenMove, TokenUpdate
from backend.app.modules.games.services import game_state_access as access
from backend.app.modules.maps.models import CampaignMap, MapHex, MapLayer, Token


async def _lock_map(session: AsyncSession, map_id: UUID, context: access.GameStateContext) -> None:
	statement = (
		select(CampaignMap)
		.where(CampaignMap.id == map_id)
		.options(lazyload("*"))
		.with_for_update()
		.execution_options(populate_existing=True)
	)
	campaign_map = (await session.execute(statement)).scalar_one_or_none()

	if campaign_map is None:
		raise errors.GameNotFound("Указанная карта не найдена")

	if campaign_map.game_id != context.game.id:
		raise errors.InvalidGameInput("Карта не принадлежит игре этой сессии")

	if campaign_map.session_id is not None and campaign_map.session_id != context.game_session.id:
		raise errors.InvalidGameInput("Карта привязана к другой игровой сессии")

async def _validate_links(session: AsyncSession, context: access.GameStateContext, values: dict) -> None:
	sheet_id = values.get("character_sheet_id")

	if sheet_id is not None:
		sheets = CharacterSheet.__table__
		statement = select(sheets.c.game_id).where(sheets.c.id == sheet_id)
		sheet_game_id = (await session.execute(statement)).scalar_one_or_none()

		if sheet_game_id != context.game.id:
			raise errors.InvalidGameInput("Лист персонажа не найден в этой игре")

	npc_id = values.get("npc_id")

	if npc_id is not None:
		npcs = NPC.__table__
		statement = select(npcs.c.system_id, npcs.c.owner_id, npcs.c.visibility_scope, npcs.c.is_active).where(npcs.c.id == npc_id)
		npc = (await session.execute(statement)).mappings().one_or_none()

		if npc is None or npc["system_id"] != context.game.system_id or not npc["is_active"]:
			raise errors.InvalidGameInput("НПС не найден среди активных записей этой игровой системы")

		if npc["owner_id"] != context.game.master_id and npc["visibility_scope"] != "public":
			raise errors.GameAccessDenied("НПС недоступен мастеру этой игры")

async def _token_context(session: AsyncSession, token_id: UUID, actor_id: UUID, *, master_only: bool, extra_map_id: UUID | None = None) -> tuple:
	access.require_clean_session(session)
	snapshot_statement = select(Token.session_id, Token.current_map_id).where(Token.id == token_id)
	snapshot = (await session.execute(snapshot_statement)).one_or_none()

	if snapshot is None:
		raise errors.GameNotFound("Токен не найден")

	session_id, previous_map_id = snapshot
	context = await access.get_session_context(session, session_id, actor_id, write=True, master_only=master_only, require_active=True)
	map_ids = {value for value in (previous_map_id, extra_map_id) if value is not None}

	for map_id in sorted(map_ids):
		await _lock_map(session, map_id, context)

	token_statement = (
		select(Token)
		.where(Token.id == token_id)
		.options(lazyload("*"))
		.with_for_update()
		.execution_options(populate_existing=True)
	)
	token = (await session.execute(token_statement)).scalar_one_or_none()

	if token is None:
		raise errors.GameNotFound("Токен не найден")

	if token.session_id != session_id or token.current_map_id != previous_map_id:
		raise errors.GameStateConflict("Размещение токена изменилось. Обновите состояние стола")

	return token, context

def _can_control_token(token: Token, actor_id: UUID, context: access.GameStateContext) -> bool:
	if context.is_master:
		return True

	if not token.is_visible_to_players:
		return False

	return token.owner_id == actor_id or actor_id in (token.controlled_by_ids or [])

async def create_token(session: AsyncSession, master_id: UUID, data: TokenCreate) -> Token:
	context = await access.get_session_context(session, data.session_id, master_id, write=True, master_only=True, require_active=True)

	if data.current_map_id is not None:
		await _lock_map(session, data.current_map_id, context)

	values = data.model_dump()
	await _validate_links(session, context, values)
	token = Token(owner_id=master_id, **values)
	session.add(token)
	await session.flush()
	return token

async def list_tokens_for_session(session: AsyncSession, session_id: UUID, viewer_id: UUID) -> list[Token]:
	context = await access.get_session_context(session, session_id, viewer_id)
	statement = (
		select(Token)
		.where(Token.session_id == session_id)
		.options(lazyload("*"))
		.order_by(Token.created_at, Token.id)
		.execution_options(populate_existing=True)
	)

	if not context.is_master:
		statement = statement.where(Token.is_visible_to_players.is_(True))

	return list((await session.execute(statement)).scalars().all())

async def update_token(session: AsyncSession, token_id: UUID, master_id: UUID, data: TokenUpdate) -> Token:
	changes = data.model_dump(exclude_unset=True)
	token, context = await _token_context(session, token_id, master_id, master_only=True, extra_map_id=changes.get("current_map_id"))
	await _validate_links(session, context, changes)

	if "current_map_id" in changes and (changes["current_map_id"] != token.current_map_id or changes["current_map_id"] is None):
		token.current_hex_id = None

	for name, value in changes.items():
		setattr(token, name, value)

	await session.flush()
	return token

async def move_token(session: AsyncSession, token_id: UUID, mover_id: UUID, data: TokenMove) -> Token:
	token, context = await _token_context(session, token_id, mover_id, master_only=False)

	if not _can_control_token(token, mover_id, context):
		raise errors.GameAccessDenied("Вы не можете перемещать этот токен")

	if data.hex_id is not None:
		if token.current_map_id is None:
			raise errors.GameStateConflict("Перед перемещением на гекс назначьте токену карту")

		statement = (
			select(MapHex.id)
			.join(MapLayer, MapLayer.id == MapHex.layer_id)
			.where(MapHex.id == data.hex_id, MapLayer.map_id == token.current_map_id)
		)
		target_hex_id = (await session.execute(statement)).scalar_one_or_none()

		if target_hex_id is None:
			raise errors.InvalidGameInput("Гекс не найден на текущей карте токена")
	else:
		target_hex_id = None

	token.current_hex_id = target_hex_id
	token.grid_x = data.grid_x
	token.grid_y = data.grid_y
	await session.flush()
	return token

async def delete_token(session: AsyncSession, token_id: UUID, master_id: UUID) -> None:
	token, _ = await _token_context(session, token_id, master_id, master_only=True)
	await session.delete(token)
	await session.flush()