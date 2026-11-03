# backend/app/modules/games/services/initiative_service.py

"""Хранение и ручное переключение очереди без правил конкретной системы.

Переданный порядок сохраняется как есть.
Выполняет flush, но не commit и не rollback.
"""

from __future__ import annotations
from copy import deepcopy
from math import isfinite
from uuid import UUID
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import lazyload
from backend.app.modules.games import errors
from backend.app.modules.games.models.lobby import InitiativeTracker
from backend.app.modules.games.schemas.game_state import DB_INT_MAX, TurnOrderCreate
from backend.app.modules.games.services import game_state_access as access


async def _get_tracker(session: AsyncSession, session_id: UUID, *, lock: bool = False) -> InitiativeTracker | None:
	statement = (
		select(InitiativeTracker)
		.where(InitiativeTracker.session_id == session_id)
		.options(lazyload("*"))
		.execution_options(populate_existing=True)
	)

	if lock:
		statement = statement.with_for_update()

	return (await session.execute(statement)).scalar_one_or_none()

def _validate_tracker(tracker: InitiativeTracker) -> list[dict]:
	order = tracker.turn_order_json

	if not isinstance(order, list) or any(not isinstance(item, dict) for item in order):
		raise errors.GameStateConflict("Сохранённая очередь ходов некорректна")

	if type(tracker.current_index) is not int or type(tracker.round_number) is not int:
		raise errors.GameStateConflict("Сохранённое положение очереди некорректно")

	if not 1 <= tracker.round_number <= DB_INT_MAX:
		raise errors.GameStateConflict("Сохранённый номер раунда некорректен")

	if order and not 0 <= tracker.current_index < len(order):
		raise errors.GameStateConflict("Текущий ход находится за пределами очереди")

	if not order and tracker.current_index != 0:
		raise errors.GameStateConflict("Положение пустой очереди некорректно")

	return order

def _public_entry(item: dict) -> dict:
	name = item.get("name")
	initiative = item.get("initiative")

	if not isinstance(name, str):
		name = None

	if type(initiative) not in (int, float):
		initiative = None
	elif isinstance(initiative, float) and not isfinite(initiative):
		initiative = None

	return {"name": name, "initiative": initiative}

async def get_combat_state(session: AsyncSession, session_id: UUID, viewer_id: UUID) -> dict:
	context = await access.get_session_context(session, session_id, viewer_id)
	tracker = await _get_tracker(session, session_id)

	if tracker is None:
		return {
			"session_id": session_id,
			"session_active": context.game_session.is_active,
			"combat_active": False,
			"turn_order": [],
			"current_index": None,
			"round_number": None,
		}

	order = _validate_tracker(tracker)
	return {
		"session_id": session_id,
		"session_active": context.game_session.is_active,
		"combat_active": tracker.is_active,
		"turn_order": [_public_entry(item) for item in order],
		"current_index": tracker.current_index if order else None,
		"round_number": tracker.round_number,
	}

async def start_combat(session: AsyncSession, session_id: UUID, master_id: UUID, combatants: list[dict]) -> InitiativeTracker:
	await access.get_session_context(session, session_id, master_id, write=True, master_only=True, require_active=True)

	try:
		prepared = TurnOrderCreate(entries=combatants)
	except ValidationError as error:
		raise errors.InvalidGameInput("Передайте непустую очередь из JSON-объектов допустимого размера") from error

	if await _get_tracker(session, session_id, lock=True) is not None:
		raise errors.GameStateConflict("Для этой сессии уже сохранена очередь ходов")

	tracker = InitiativeTracker(
		session_id=session_id,
		turn_order_json=deepcopy(prepared.entries),
		current_index=0,
		round_number=1,
		is_active=True,
	)
	session.add(tracker)
	await session.flush()
	return tracker

async def next_turn(session: AsyncSession, session_id: UUID, master_id: UUID) -> InitiativeTracker:
	await access.get_session_context(session, session_id, master_id, write=True, master_only=True, require_active=True)
	tracker = await _get_tracker(session, session_id, lock=True)

	if tracker is None:
		raise errors.GameNotFound("Очередь ходов не найдена")

	order = _validate_tracker(tracker)

	if not tracker.is_active:
		raise errors.GameStateConflict("Очередь ходов неактивна")

	if not order:
		raise errors.GameStateConflict("Очередь ходов пуста")

	next_index = tracker.current_index + 1
	next_round = tracker.round_number

	if next_index >= len(order):
		if next_round >= DB_INT_MAX:
			raise errors.GameStateConflict("Достигнут предел хранения номера раунда")

		next_index = 0
		next_round += 1

	tracker.current_index = next_index
	tracker.round_number = next_round
	await session.flush()
	return tracker

async def end_combat(session: AsyncSession, session_id: UUID, master_id: UUID) -> None:
	await access.get_session_context(session, session_id, master_id, write=True, master_only=True)
	tracker = await _get_tracker(session, session_id, lock=True)

	if tracker is None:
		raise errors.GameNotFound("Очередь ходов не найдена")

	await session.delete(tracker)
	await session.flush()