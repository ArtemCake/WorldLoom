# backend/app/modules/catalog/service.py

"""Карточки игровых систем без зависимости от HTTP и фиксации транзакций."""

from uuid import UUID
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import lazyload
from backend.app.modules.catalog.errors import CatalogConflict, CatalogNotFound
from backend.app.modules.catalog.schemas import GameSystemCreate, GameSystemUpdate
from backend.app.modules.game_systems.models.game_systems import GameSystem


async def list_active_systems(session: AsyncSession) -> list[GameSystem]:
	query = select(GameSystem).options(lazyload("*")).where(GameSystem.is_active.is_(True)).order_by(GameSystem.name)
	result = await session.execute(query)
	return list(result.scalars().all())

async def list_all_systems(session: AsyncSession) -> list[GameSystem]:
	query = select(GameSystem).options(lazyload("*")).order_by(GameSystem.is_active.desc(), GameSystem.name, GameSystem.id)
	result = await session.execute(query)
	return list(result.scalars().all())

async def get_game_system(session: AsyncSession, system_id: UUID, *, active_only: bool = False, for_update: bool = False) -> GameSystem:
	query = select(GameSystem).options(lazyload("*")).where(GameSystem.id == system_id)

	if active_only:
		query = query.where(GameSystem.is_active.is_(True))

	if for_update:
		query = query.with_for_update().execution_options(populate_existing=True)

	system = (await session.execute(query)).scalar_one_or_none()

	if system is None:
		raise CatalogNotFound("Игровая система не найдена.")

	return system

async def _check_system_unique(session: AsyncSession, name: str, slug: str, exclude_id: UUID | None = None) -> None:
	query = select(GameSystem.id).where(or_(GameSystem.name == name, GameSystem.slug == slug))

	if exclude_id is not None:
		query = query.where(GameSystem.id != exclude_id)

	existing = (await session.execute(query.limit(1))).scalar_one_or_none()

	if existing is not None:
		raise CatalogConflict("Игровая система с таким названием или slug уже существует.")

async def create_game_system(session: AsyncSession, data: GameSystemCreate) -> GameSystem:
	await _check_system_unique(session, data.name, data.slug)

	system = GameSystem(**data.model_dump())
	session.add(system)
	await session.flush()
	await session.refresh(system)
	return system

async def update_game_system(session: AsyncSession, system_id: UUID, data: GameSystemUpdate) -> GameSystem:
	system = await get_game_system(session, system_id, for_update=True)
	changes = data.model_dump(exclude_unset=True)

	if not changes:
		return system

	if "name" in changes or "slug" in changes:
		await _check_system_unique(session, changes.get("name", system.name), changes.get("slug", system.slug), exclude_id=system.id)

	for field, value in changes.items():
		setattr(system, field, value)

	await session.flush()
	await session.refresh(system)
	return system
