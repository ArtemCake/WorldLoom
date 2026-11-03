# backend/app/modules/characters/services/content_service.py

"""Заклинания и инвентарь листа без самостоятельной фиксации транзакций."""

from uuid import UUID
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import lazyload
from backend.app.modules.catalog.models.equipment import Equipment
from backend.app.modules.catalog.models.magic import Spell
from backend.app.modules.characters.schemas.content_schemas import (InventoryItemIn, InventoryItemRead, InventoryItemUpdate, SpellOnSheetIn,
                                                            SpellOnSheetRead, SpellOnSheetUpdate)
from backend.app.modules.characters.errors import CharacterNotFound, CharacterStateConflict, InvalidCharacterStateChange
from backend.app.modules.characters.models import CharacterInventory, CharacterSheet, CharacterSheetSpell
from backend.app.modules.characters.services.service import _get_sheet, _require_clean_session
from backend.app.modules.games.models.lobby import Game


_MAX_INTEGER = 2147483647

async def _require_catalog_entry(session: AsyncSession, model: type[Spell] | type[Equipment], entry_id: UUID, sheet: CharacterSheet,
                                 user_id: UUID) -> None:
	"""Разрешить добавление активной собственной или публичной записи системы игры."""
	system_id = await session.scalar(select(Game.system_id).where(Game.id == sheet.game_id))
	statement = (
		select(model.id)
		.where(
			model.id == entry_id,
			model.system_id == system_id,
			model.is_active.is_(True),
			or_(model.owner_id == user_id, model.visibility_scope == "public"),
			)
		.with_for_update(read=True)
	)

	if await session.scalar(statement) is None:
		raise CharacterNotFound("Доступная запись каталога не найдена.")

async def _find_spell(session: AsyncSession, sheet_id: UUID, link_id: UUID) -> CharacterSheetSpell:
	statement = (
		select(CharacterSheetSpell)
		.where(CharacterSheetSpell.id == link_id, CharacterSheetSpell.sheet_id == sheet_id)
		.options(lazyload("*"))
		.execution_options(populate_existing=True)
		.with_for_update()
	)
	link = (await session.execute(statement)).scalar_one_or_none()

	if link is None:
		raise CharacterNotFound("Заклинание на листе не найдено.")

	return link

async def _find_item(session: AsyncSession, sheet_id: UUID, item_id: UUID) -> CharacterInventory:
	statement = (
		select(CharacterInventory)
		.where(CharacterInventory.sheet_id == sheet_id, CharacterInventory.item_id == item_id)
		.options(lazyload("*"))
		.execution_options(populate_existing=True)
		.with_for_update()
	)
	entry = (await session.execute(statement)).scalar_one_or_none()

	if entry is None:
		raise CharacterNotFound("Предмет в инвентаре не найден.")

	return entry

async def _flush_content_change(session: AsyncSession, sheet: CharacterSheet) -> None:
	"""Отразить изменение коллекций в общей ревизии листа."""
	sheet.revision += 1
	await session.flush()

async def list_sheet_spells(session: AsyncSession, sheet_id: UUID, user_id: UUID) -> list[SpellOnSheetRead]:
	_require_clean_session(session)
	sheet = await _get_sheet(session, sheet_id, user_id, for_update=False)
	statement = (
		select(CharacterSheetSpell)
		.where(CharacterSheetSpell.sheet_id == sheet.id)
		.options(lazyload("*"))
		.order_by(CharacterSheetSpell.id)
	)
	links = (await session.execute(statement)).scalars().all()
	return [SpellOnSheetRead.model_validate(link) for link in links]

async def add_spell_to_sheet(session: AsyncSession, sheet_id: UUID, user_id: UUID, data: SpellOnSheetIn) -> SpellOnSheetRead:
	data = SpellOnSheetIn.model_validate(data)
	_require_clean_session(session)
	sheet = await _get_sheet(session, sheet_id, user_id, for_update=True)
	await _require_catalog_entry(session, Spell, data.spell_id, sheet, user_id)

	existing_id = await session.scalar(
		select(CharacterSheetSpell.id)
		.where(CharacterSheetSpell.sheet_id == sheet.id, CharacterSheetSpell.spell_id == data.spell_id)
	)

	if existing_id is not None:
		raise CharacterStateConflict("Заклинание уже добавлено на лист.")

	link = CharacterSheetSpell(sheet_id=sheet.id, **data.model_dump())
	session.add(link)
	await _flush_content_change(session, sheet)
	return SpellOnSheetRead.model_validate(link)

async def update_sheet_spell(session: AsyncSession, sheet_id: UUID, link_id: UUID, user_id: UUID, data: SpellOnSheetUpdate) -> SpellOnSheetRead:
	data = SpellOnSheetUpdate.model_validate(data)
	_require_clean_session(session)
	sheet = await _get_sheet(session, sheet_id, user_id, for_update=True)
	link = await _find_spell(session, sheet.id, link_id)
	changed = False

	for field, value in data.model_dump(exclude_unset=True).items():
		if getattr(link, field) != value:
			setattr(link, field, value)
			changed = True

	if changed:
		await _flush_content_change(session, sheet)

	return SpellOnSheetRead.model_validate(link)

async def remove_spell_from_sheet(session: AsyncSession, sheet_id: UUID, link_id: UUID, user_id: UUID) -> None:
	_require_clean_session(session)
	sheet = await _get_sheet(session, sheet_id, user_id, for_update=True)
	link = await _find_spell(session, sheet.id, link_id)
	await session.delete(link)
	await _flush_content_change(session, sheet)

async def list_sheet_inventory(session: AsyncSession, sheet_id: UUID, user_id: UUID) -> list[InventoryItemRead]:
	_require_clean_session(session)
	sheet = await _get_sheet(session, sheet_id, user_id, for_update=False)
	statement = (
		select(CharacterInventory)
		.where(CharacterInventory.sheet_id == sheet.id)
		.options(lazyload("*"))
		.order_by(CharacterInventory.item_id)
	)
	entries = (await session.execute(statement)).scalars().all()
	return [InventoryItemRead.model_validate(entry) for entry in entries]

async def add_item_to_inventory(session: AsyncSession, sheet_id: UUID, user_id: UUID, data: InventoryItemIn) -> InventoryItemRead:
	data = InventoryItemIn.model_validate(data)
	_require_clean_session(session)
	sheet = await _get_sheet(session, sheet_id, user_id, for_update=True)
	await _require_catalog_entry(session, Equipment, data.item_id, sheet, user_id)

	statement = (
		select(CharacterInventory)
		.where(CharacterInventory.sheet_id == sheet.id, CharacterInventory.item_id == data.item_id)
		.options(lazyload("*"))
		.execution_options(populate_existing=True)
		.with_for_update()
	)
	entry = (await session.execute(statement)).scalar_one_or_none()

	if entry is None:
		entry = CharacterInventory(sheet_id=sheet.id, **data.model_dump())
		session.add(entry)
	else:
		quantity = entry.quantity + data.quantity

		if quantity > _MAX_INTEGER:
			raise InvalidCharacterStateChange("Суммарное количество предметов превышает допустимое значение.")

		entry.quantity = quantity

	await _flush_content_change(session, sheet)
	return InventoryItemRead.model_validate(entry)

async def update_inventory_item(session: AsyncSession, sheet_id: UUID, item_id: UUID, user_id: UUID, data: InventoryItemUpdate) -> InventoryItemRead:
	data = InventoryItemUpdate.model_validate(data)
	_require_clean_session(session)
	sheet = await _get_sheet(session, sheet_id, user_id, for_update=True)
	entry = await _find_item(session, sheet.id, item_id)
	changed = False

	for field, value in data.model_dump(exclude_unset=True).items():
		if getattr(entry, field) != value:
			setattr(entry, field, value)
			changed = True

	if changed:
		await _flush_content_change(session, sheet)

	return InventoryItemRead.model_validate(entry)

async def remove_item_from_inventory(session: AsyncSession, sheet_id: UUID, item_id: UUID, user_id: UUID) -> None:
	_require_clean_session(session)
	sheet = await _get_sheet(session, sheet_id, user_id, for_update=True)
	entry = await _find_item(session, sheet.id, item_id)
	await session.delete(entry)
	await _flush_content_change(session, sheet)
