# backend/app/modules/characters/services/content_selection_service.py

"""Выбор контента и происхождение выданных свойств (Этап E).

Связывает создание персонажа, выдачу свойств и предметные
определения каталога (§9, §13).

Единственный путь записи числовых значений сохраняется: сервис
не подменяет SheetState и не дублирует вычислительное ядро. Он
возвращает новое состояние, а сохранение и ревизию выполняет
вызывающий код через существующий update_character_state (§1.2).

Принципы договора:
- один источник не применяется повторно при повторном сохранении (§9);
- недопустимые выборы не принимаются: результат проверяет ядро (§9);
- отзыв снимает только свойства данного источника, не затрагивая
  одноимённые свойства других источников (§13);
- категории каталога являются данными, а не жёсткой схемой:
  классовая модель не навязывается всем играм (§13).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.modules.catalog.models.character_building import (
    CharacterClass,
    Background,
    Feat,
    Origin,
    Race,
    Subclass,
)
from backend.app.modules.catalog.models.equipment import Equipment
from backend.app.modules.characters.errors import (
    CharacterNotFound,
    CharacterStateConflict,
    InvalidCharacterStateChange,
)
from backend.app.modules.characters.models import (
    Character,
    CharacterContentSelection,
    CharacterSheet,
    SheetAttributeProvenance,
)
from backend.app.modules.characters.schemas.selection_schemas import (
    ContentGrantIn,
    ContentSelectionIn,
)
from backend.app.modules.game_systems.schemas.game_rules import (
    RulesProfile,
    SheetState,
)
from backend.app.modules.game_systems.rules.rules_engine import (
    evaluate_sheet_state,
)

# Техническое ограничение: длина кода источника, а не игровое правило.
_SOURCE_MODELS: dict[str, type] = {
	"race": Race,
	"character_class": CharacterClass,
	"subclass": Subclass,
	"background": Background,
	"origin": Origin,
	"feat": Feat,
	"equipment": Equipment,
}

# Источник может не иметь элемента каталога.
_NON_CATALOG_SOURCES = {"manual", "base", "effect"}


def _owner_key(sheet: CharacterSheet | Character) -> UUID:
	"""Вернуть идентификатор владельца происхождения.

	Происхождение принадлежит ровно одному объекту: игровому листу
	или собственному шаблону (§14.1).
	"""
	if isinstance(sheet, CharacterSheet):
		return sheet.id

	if isinstance(sheet, Character):
		return sheet.id

	raise TypeError(f"Неподдерживаемый владелец состояния: {type(sheet).__name__}")


def _is_catalog_source(source_type: str) -> bool:
	return source_type in _SOURCE_MODELS


async def _require_active_catalog_entry(
	session: AsyncSession,
	source_type: str,
	source_id: UUID,
	system_id: UUID,
) -> None:
	"""Проверить активный элемент каталога нужной системы (§9).

	Недопустимый выбор не принимается: запись должна существовать,
	принадлежать той же системе и быть активной.
	"""
	model = _SOURCE_MODELS[source_type]

	statement = (
		select(model.id)
		.where(
			model.id == source_id,
			model.system_id == system_id,
			model.is_active.is_(True),
		)
	)

	if await session.scalar(statement) is None:
		raise CharacterNotFound(
			f"Активный элемент каталога не найден: {source_type} {source_id}"
		)


def _reverse_grant(attributes: dict[str, int], record: SheetAttributeProvenance) -> None:
	"""Снять влияние одного гранта из словаря значений.

	Для add вычитание возвращает выданное. Для set восстанавливается
	значение previous_value, записанное в момент выдачи (§14.1).
	"""
	if record.mode == "add":
		attributes[record.code] = attributes.get(record.code, 0) - record.amount
	else:
		attributes[record.code] = record.previous_value


def _apply_grant(attributes: dict[str, int], record: SheetAttributeProvenance) -> None:
	"""Наложить один грант на словарь значений."""
	if record.mode == "add":
		attributes[record.code] = attributes.get(record.code, 0) + record.amount
	else:
		attributes[record.code] = record.amount


async def _load_provenance(
	session: AsyncSession,
	owner_id: UUID,
) -> list[SheetAttributeProvenance]:
	"""Прочитать все записи происхождения владельца."""
	statement = (
		select(SheetAttributeProvenance)
		.where(SheetAttributeProvenance.owner_key == owner_id)
		.order_by(
			SheetAttributeProvenance.code,
			SheetAttributeProvenance.source_type,
		)
	)
	return list((await session.execute(statement)).scalars().all())


async def _load_source_records(
	session: AsyncSession,
	owner_id: UUID,
	source_type: str,
	source_id: UUID | None,
) -> list[SheetAttributeProvenance]:
	"""Прочитать выдачи конкретного источника."""
	statement = (
		select(SheetAttributeProvenance)
		.where(
			SheetAttributeProvenance.owner_key == owner_id,
			SheetAttributeProvenance.source_type == source_type,
			SheetAttributeProvenance.source_id == source_id,
		)
		.order_by(SheetAttributeProvenance.code)
	)
	return list((await session.execute(statement)).scalars().all())


async def apply_content_grants(
	session: AsyncSession,
	sheet: CharacterSheet | Character,
	profile: RulesProfile,
	current_state: SheetState,
	source_type: str,
	source_id: UUID | None,
	grants: list[ContentGrantIn],
) -> SheetState:
	"""Применить выдачу одного источника к текущему состоянию.

	Используется дельта-семантика: сначала снимается прежнее влияние
	этого источника, затем накладывается новое. Поэтому повторное
	сохранение того же источника не удваивает выдачу (§9) и не
	требуется отдельное «состояние основы», то есть второй источник
	правды (§1.2). Выдачи прочих источников не затрагиваются (§13).

	Функция возвращает новое состояние и обновляет записи
	происхождения. Значение сохраняет и фиксирует ревизию вызывающий
	код через существующий путь записи.
	"""
	owner_id = _owner_key(sheet)

	for grant in grants:
		if grant.code not in profile.calculations.attributes:
			raise InvalidCharacterStateChange(
				f"Неизвестный исходный показатель: {grant.code}"
			)

		if grant.source_type != source_type:
			raise InvalidCharacterStateChange(
				"Тип источника в гранте не совпадает с выдающим"
			)

		if grant.source_id != source_id:
			raise InvalidCharacterStateChange(
				"Идентификатор источника в гранте не совпадает с выдающим"
			)

	# set от двух разных источников для одного кода дать
	# однозначный результат не может. Предпочитаем безопасный
	# отказ с диагностикой, а не невидимый порядок применения (§14.3).
	set_codes = sorted({grant.code for grant in grants if grant.mode == "set"})

	if set_codes:
		conflict = await session.scalar(
			select(SheetAttributeProvenance.id)
			.where(
				SheetAttributeProvenance.owner_key == owner_id,
				SheetAttributeProvenance.mode == "set",
				SheetAttributeProvenance.source_type != source_type,
				SheetAttributeProvenance.code.in_(set_codes),
			)
		)

		if conflict is not None:
			raise InvalidCharacterStateChange(
				"Показатель уже установлен другим источником; "
				"одновременное замещение не поддержано"
			)

	attributes = dict(current_state.attributes)

	# Снимаем прежнее влияние этого же источника в копии значений.
	# Изменения в БД попадают только после проверки ядром, поэтому
	# откат не требуется и транзакция остаётся у вызывающего кода.
	old_records = await _load_source_records(session, owner_id, source_type, source_id)

	for record in old_records:
		_reverse_grant(attributes, record)

	# Формируем новые выдачи поверх снятого состояния.
	new_records: list[SheetAttributeProvenance] = []

	for grant in grants:
		record = SheetAttributeProvenance(
			character_sheet_id=owner_id if isinstance(sheet, CharacterSheet) else None,
			character_id=owner_id if isinstance(sheet, Character) else None,
			code=grant.code,
			source_type=source_type,
			source_id=source_id,
			mode=grant.mode,
			amount=grant.amount,
			previous_value=attributes.get(grant.code, 0),
		)
		_apply_grant(attributes, record)
		new_records.append(record)

	updated = SheetState(attributes=attributes)

	try:
		evaluate_sheet_state(profile, updated)
	except ValueError as exc:
		# Недопустимое решение не сохраняется как действующее (§9).
		raise InvalidCharacterStateChange(
			f"Выдача не соответствует правилам: {exc}"
		) from exc

	for record in old_records:
		await session.delete(record)

	# Удаления фиксируются раньше вставок: общий flush выполнил бы
	# INSERT до DELETE, и новый грант того же источника попал бы
	# в действующий уникальный индекс.
	await session.flush()

	for record in new_records:
		session.add(record)

	await session.flush()
	return updated


async def withdraw_source_grants(
	session: AsyncSession,
	sheet: CharacterSheet | Character,
	profile: RulesProfile,
	current_state: SheetState,
	source_type: str,
	source_id: UUID | None,
) -> SheetState:
	"""Отозвать выдачу одного источника (§13).

	Снимаются только свойства данного источника. Одноимённые свойства
	других источников остаются без изменений.
	"""
	owner_id = _owner_key(sheet)
	attributes = dict(current_state.attributes)

	target = await _load_source_records(session, owner_id, source_type, source_id)

	if not target:
		return current_state

	for record in target:
		_reverse_grant(attributes, record)

	updated = SheetState(attributes=attributes)

	try:
		evaluate_sheet_state(profile, updated)
	except ValueError as exc:
		raise InvalidCharacterStateChange(
			f"Отзыв делает состояние недействительным: {exc}"
		) from exc

	for record in target:
		await session.delete(record)

	await session.flush()
	return updated


async def select_content(
	session: AsyncSession,
	character: Character,
	system_id: UUID,
	selection: ContentSelectionIn,
) -> CharacterContentSelection:
	"""Зарегистрировать выбор элемента каталога (§9).

	Повторный выбор того же типа отклоняется: сначала нужно отменить
	прежний выбор, иначе зависимые решения останутся необъяснёнными.
	"""
	source_type = selection.source_type

	if _is_catalog_source(source_type):
		await _require_active_catalog_entry(
			session, source_type, selection.source_id, system_id
		)
	elif source_type in _NON_CATALOG_SOURCES:
		raise CharacterStateConflict(
			f"Источник типа {source_type} не выбирается из каталога"
		)
	else:
		raise InvalidCharacterStateChange(
			f"Неизвестный тип выбираемого источника: {source_type}"
		)

	existing = await session.scalar(
		select(CharacterContentSelection).where(
			CharacterContentSelection.character_id == character.id,
			CharacterContentSelection.source_type == source_type,
		)
	)

	if existing is not None:
		if existing.source_id == selection.source_id and existing.is_active:
			# Повтор того же выбора не создаёт дубликат (§9).
			return existing

		if existing.is_active:
			raise CharacterStateConflict(
				f"Источник типа {source_type} уже выбран. Сначала отмените его"
			)

		# Прежний выбор снят, поэтому запись переиспользуется:
		# уникальный индекс допускает лишь одну строку на тип.
		existing.source_id = selection.source_id
		existing.is_active = True
		await session.flush()
		return existing

	record = CharacterContentSelection(
		character_id=character.id,
		source_type=source_type,
		source_id=selection.source_id,
		is_active=True,
	)
	session.add(record)
	await session.flush()
	return record


async def deselect_content(
	session: AsyncSession,
	character: Character,
	source_type: str,
) -> CharacterContentSelection | None:
	"""Снять выбор элемента каталога, сохранив запись для аудита."""
	record = await session.scalar(
		select(CharacterContentSelection).where(
			CharacterContentSelection.character_id == character.id,
			CharacterContentSelection.source_type == source_type,
		)
	)

	if record is None:
		raise CharacterNotFound("Выбор не найден")

	record.is_active = False
	await session.flush()
	return record


async def list_selections(
	session: AsyncSession,
	character_id: UUID,
) -> list[CharacterContentSelection]:
	"""Вернуть активные выборы персонажа."""
	statement = (
		select(CharacterContentSelection)
		.where(
			CharacterContentSelection.character_id == character_id,
			CharacterContentSelection.is_active.is_(True),
		)
		.order_by(CharacterContentSelection.applied_at)
	)
	return list((await session.execute(statement)).scalars().all())


async def list_provenance(
	session: AsyncSession,
	sheet: CharacterSheet | Character,
) -> list[SheetAttributeProvenance]:
	"""Вернуть происхождение всех свойств владельца (§14.1)."""
	return await _load_provenance(session, _owner_key(sheet))


__all__ = [
	"apply_content_grants",
	"withdraw_source_grants",
	"select_content",
	"deselect_content",
	"list_selections",
	"list_provenance",
]
