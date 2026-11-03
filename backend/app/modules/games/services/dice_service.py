# backend/app/modules/games/services/dice_service.py

"""Сохранение и чтение бросков с проверкой доступа к игровой встрече.

Выполняет flush, но не commit и не rollback.
Контекст броска является метаданными, а не командой исполнения правил.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import lazyload

from backend.app.modules.games import errors
from backend.app.modules.games.models.lobby import DiceRoll, Party
from backend.app.modules.games.schemas.dice import DiceRollIn
from backend.app.modules.games.services import game_state_access as access
from backend.app.modules.games.services.dice_engine import DiceExpression, InvalidDiceExpression


async def _validate_party(session: AsyncSession, party_id: UUID, roller_id: UUID, context: access.GameStateContext) -> None:
	parties = Party.__table__
	statement = select(parties.c.game_id, parties.c.user_id, parties.c.is_active, parties.c.role_in_game).where(parties.c.id == party_id)
	party = (await session.execute(statement)).mappings().one_or_none()

	if party is None or party["game_id"] != context.game.id:
		raise errors.InvalidGameInput("Участник не принадлежит игре этой сессии")

	if not party["is_active"] or party["role_in_game"] == "banned":
		raise errors.GameAccessDenied("Участник не имеет активного доступа к игре")

	if party["user_id"] != roller_id and not context.is_master:
		raise errors.GameAccessDenied("Нельзя привязать бросок к другому участнику")

async def roll_dice(session: AsyncSession, session_id: UUID, roller_id: UUID, party_id: UUID | None, data: DiceRollIn) -> DiceRoll:
	try:
		expression = DiceExpression.parse(data.formula)
	except InvalidDiceExpression as error:
		raise errors.InvalidGameInput(str(error)) from error

	context = await access.get_session_context(session, session_id, roller_id, write=True, require_active=True)

	if data.is_gm_hidden and not context.is_master:
		raise errors.GameAccessDenied("Только мастер игры может выполнять скрытые броски")

	if party_id is not None:
		await _validate_party(session, party_id, roller_id, context)

	result = expression.roll()
	dice_roll = DiceRoll(
		session_id=session_id,
		roller_id=roller_id,
		party_id=party_id,
		npc_id=None,
		formula=expression.formula,
		result_total=result.result_total,
		individual_results=list(result.individual_results),
		advantage=None,
		is_gm_hidden=data.is_gm_hidden,
		context_type=data.context_type,
		context_target_id=data.context_target_id,
	)
	session.add(dice_roll)
	await session.flush()
	return dice_roll

async def list_session_rolls(session: AsyncSession, session_id: UUID, viewer_id: UUID, *, limit: int = 100, offset: int = 0) -> list[DiceRoll]:
	if type(limit) is not int or not 1 <= limit <= 500 or type(offset) is not int or not 0 <= offset <= 1_000_000:
		raise errors.InvalidGameInput("Недопустимые параметры страницы истории бросков")

	context = await access.get_session_context(session, session_id, viewer_id)
	statement = (
		select(DiceRoll)
		.where(DiceRoll.session_id == session_id)
		.options(lazyload("*"))
		.order_by(DiceRoll.created_at.desc(), DiceRoll.id.desc())
		.limit(limit)
		.offset(offset)
		.execution_options(populate_existing=True)
	)

	if not context.is_master:
		statement = statement.where(DiceRoll.is_gm_hidden.is_(False))

	return list((await session.execute(statement)).scalars().all())
