# backend/app/modules/characters/services/sheet_runtime_service.py

"""Изменение прежних полей листа без дублирования универсального состояния."""

from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.modules.characters.errors import CharacterStateConflict, CharacterStateStorageError
from backend.app.modules.characters.models import CharacterSheet
from backend.app.modules.characters.schemas.sheet_runtime import (LegacySheetRead, LegacySheetUpdate, SheetActivityRead, SheetActivityUpdate,                                                               SpellSlotsUpdate)
from backend.app.modules.characters.services.service import _get_sheet, _require_clean_session


_FIELD_MAP = {
	"death_save_successes": "death_saves_success",
	"death_save_failures": "death_saves_failure",
	"conditions": "conditions_json",
}

def _require_legacy_sheet(sheet: CharacterSheet) -> None:
	"""Не изменять прежние значения параллельно универсальному состоянию."""
	has_state = sheet.state_json is not None
	has_rules = sheet.state_rules_version_id is not None

	if has_state != has_rules:
		raise CharacterStateStorageError("Нарушена привязка состояния листа к публикации правил.")

	if has_state:
		raise CharacterStateConflict("Лист использует универсальное состояние. Прежние боевые поля изменять нельзя.")

def _check_revision(sheet: CharacterSheet, expected_revision: int) -> None:
	if sheet.revision != expected_revision:
		raise CharacterStateConflict("Лист уже изменён. Получите актуальную ревизию.")

def _legacy_read(sheet: CharacterSheet) -> LegacySheetRead:
	"""Сформировать ответ до завершения внешней транзакции."""
	try:
		return LegacySheetRead(
			id=sheet.id,
			revision=sheet.revision,
			hp_current=sheet.hp_current,
			hp_temp=sheet.hp_temp,
			death_save_successes=sheet.death_saves_success,
			death_save_failures=sheet.death_saves_failure,
			conditions=sheet.conditions_json,
			spell_slots_json=sheet.spell_slots_json,
			is_active_in_game=sheet.is_active_in_game,
		)
	except ValueError as exc:
		raise CharacterStateStorageError("Прежние поля листа имеют неподдерживаемый формат.") from exc

def _activity_read(sheet: CharacterSheet) -> SheetActivityRead:
	return SheetActivityRead(
		id=sheet.id,
		revision=sheet.revision,
		is_active_in_game=sheet.is_active_in_game,
	)

async def get_legacy_sheet(session: AsyncSession, sheet_id: UUID, user_id: UUID) -> LegacySheetRead:
	_require_clean_session(session)
	sheet = await _get_sheet(session, sheet_id, user_id, for_update=False, require_rules=False)
	_require_legacy_sheet(sheet)
	return _legacy_read(sheet)

async def update_legacy_sheet(session: AsyncSession, sheet_id: UUID, user_id: UUID, data: LegacySheetUpdate) -> LegacySheetRead:
	data = LegacySheetUpdate.model_validate(data)
	_require_clean_session(session)
	sheet = await _get_sheet(session, sheet_id, user_id, for_update=True, require_rules=False)
	_require_legacy_sheet(sheet)
	_check_revision(sheet, data.expected_revision)

	for field, value in data.model_dump(exclude_unset=True, exclude={"expected_revision"}).items():
		model_field = _FIELD_MAP.get(field, field)

		if getattr(sheet, model_field) != value:
			setattr(sheet, model_field, value)

	await session.flush()
	return _legacy_read(sheet)

async def update_spell_slots(session: AsyncSession, sheet_id: UUID, user_id: UUID, data: SpellSlotsUpdate) -> LegacySheetRead:
	data = SpellSlotsUpdate.model_validate(data)
	_require_clean_session(session)
	sheet = await _get_sheet(session, sheet_id, user_id, for_update=True, require_rules=False)
	_require_legacy_sheet(sheet)
	_check_revision(sheet, data.expected_revision)

	if sheet.spell_slots_json != data.slots:
		sheet.spell_slots_json = data.model_dump()["slots"]

	await session.flush()
	return _legacy_read(sheet)

async def update_sheet_activity(session: AsyncSession, sheet_id: UUID, user_id: UUID, data: SheetActivityUpdate) -> SheetActivityRead:
	data = SheetActivityUpdate.model_validate(data)
	_require_clean_session(session)
	sheet = await _get_sheet(session, sheet_id, user_id, for_update=True, require_rules=False)
	_check_revision(sheet, data.expected_revision)

	if sheet.is_active_in_game != data.is_active_in_game:
		sheet.is_active_in_game = data.is_active_in_game

	await session.flush()
	return _activity_read(sheet)