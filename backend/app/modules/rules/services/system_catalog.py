# backend/app/modules/rules/services/system_catalog.py

"""Варианты игровых систем для читательского каталога и авторской мастерской."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.modules.game_systems.models.game_systems import GameSystem


async def list_active_system_options(session: AsyncSession) -> list[dict[str, str]]:
	"""Прочитать активные системы для существующего читательского каталога."""
	statement = select(GameSystem.id, GameSystem.name).where(GameSystem.is_active.is_(True))
	statement = statement.order_by(func.lower(GameSystem.name), GameSystem.id)
	result = await session.execute(statement)

	return [{"id": str(row["id"]), "name": row["name"]} for row in result.mappings().all()]

async def list_author_system_options(session: AsyncSession) -> list[dict[str, str]]:
	"""Прочитать системы для мастерской; разрешение проверяет вызывающий слой."""
	statement = select(GameSystem.id, GameSystem.name)
	statement = statement.order_by(func.lower(GameSystem.name), GameSystem.id)
	result = await session.execute(statement)

	return [{"id": str(row["id"]), "name": row["name"]} for row in result.mappings().all()]