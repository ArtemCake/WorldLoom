# backend/app/modules/characters/services/effect_service.py

"""Экземпляры эффектов на цели и журнал причин (Этап F3, §12).

Договор (§12) и как он выполнен:
- эффект имеет отдельный экземпляр, источник, цель, изменения,
  условия, правила сочетания, начало, длительность и события
  прекращения — всё это поля EffectInstance;
- удаление одного экземпляра не снимает другой только из-за
  совпадения названия: идентичность даёт первичный ключ экземпляра,
  а снятие всегда адресует конкретный id;
- сочетание модификаторов определяют явные правила, порядок загрузки
  из БД результат не задаёт — свёртку выполняет ядро
  effect_stacking.combine_modifier;
- повтор обработки одного события не снимает эффект дважды и не
  создаёт его копию: наложение идемпотентно по application_key;
- причины наложения, продления, подавления и снятия сохраняются в
  журнале effect_changes.

Итог свёртки в БД не хранится: он вычисляется из активных
экземпляров, поэтому второго источника правды нет (§1.2).

Разделение ответственности: сервис — единственный путь записи;
транзакция принадлежит вызывающему коду (commit/rollback нет).

Длительность и события прекращения хранятся как данные. Течение
игрового времени и автоматическое истечение относятся к исполнению
процедур (§30#6, этап H) и здесь не вычисляются.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.modules.characters.errors import (
	CharacterNotFound,
	InvalidCharacterStateChange,
)
from backend.app.modules.characters.models import (
	Character,
	CharacterSheet,
	EffectChange,
	EffectInstance,
)
from backend.app.modules.characters.schemas.effect_schemas import (
	EffectAggregateRead,
	EffectAggregationRead,
	EffectChangeRead,
	EffectChangesRead,
	EffectExtendIn,
	EffectInstanceApplyIn,
	EffectInstanceRead,
	EffectInstancesRead,
	EffectModifierIn,
	EffectOutcomeRead,
)
from backend.app.modules.game_systems.rules.effect_stacking import (
	EffectModifier,
	combine_modifier,
)

StateOwner = Character | CharacterSheet


def _require_clean_session(session: AsyncSession) -> None:
	"""Не блокировать строки поверх несохранённых ORM-изменений."""
	if session.new or session.dirty or session.deleted:
		raise RuntimeError(
			"Операция эффектов требует сессии без ожидающих ORM-изменений"
		)


def _owner_key(owner: StateOwner) -> UUID:
	"""Идентификатор цели: лист или собственный шаблон (§14.1)."""
	if owner is None:
		raise CharacterNotFound("Цель эффекта не указана")

	if isinstance(owner, (CharacterSheet, Character)):
		return owner.id

	raise CharacterNotFound(f"Цель эффекта не найдена: {type(owner).__name__}")


def _owner_columns(owner: StateOwner) -> dict[str, UUID | None]:
	"""Распределить владельца по колонкам внешнего ключа (§14.1)."""
	if isinstance(owner, CharacterSheet):
		return {"character_sheet_id": owner.id, "character_id": None}

	return {"character_sheet_id": None, "character_id": owner.id}


def _now() -> datetime:
	return datetime.now(timezone.utc)


async def _lock_owner(session: AsyncSession, owner_id: UUID) -> None:
	"""Сериализовать операции одного владельца.

	Блокировка строки цели нужна, чтобы одновременные наложения с одним
	application_key не создали копию экземпляра (§12), а одновременное
	снятие не было засчитано дважды.
	"""
	for model in (CharacterSheet, Character):
		locked = (
			await session.execute(
				select(model.id)
				.where(model.id == owner_id)
				.with_for_update()
			)
		).scalar_one_or_none()

		if locked is not None:
			return

	raise CharacterNotFound(f"Цель эффекта не найдена: {owner_id}")


async def _load_instance(
	session: AsyncSession,
	owner_id: UUID,
	instance_id: UUID,
) -> EffectInstance:
	"""Прочитать экземпляр цели, иначе объяснить отсутствие."""
	instance = (
		await session.execute(
			select(EffectInstance).where(
				EffectInstance.id == instance_id,
				EffectInstance.owner_key == owner_id,
			)
		)
	).scalar_one_or_none()

	if instance is None:
		raise CharacterNotFound(f"Экземпляр эффекта не найден: {instance_id}")

	return instance


def _validate_modifiers(modifiers: list[EffectModifierIn]) -> None:
	"""Проверить изменения эффекта до записи (§12).

	Ядро проверяет известные правила сочетания, диапазоны значений и
	неповторимость идентичности. Временные идентификаторы нужны только
	для проверки: идентичность экземпляру даёт его первичный ключ.
	"""
	if not modifiers:
		raise InvalidCharacterStateChange("Эффект должен иметь хотя бы одно изменение")

	duplicated = sorted({
		modifier.code for modifier in modifiers
		if [item.code for item in modifiers].count(modifier.code) > 1
	})

	if duplicated:
		# Два изменения одного показателя в одном экземпляре пришлось бы
		# разделять искусственной идентичностью: проще требовать два
		# экземпляра, у каждого из которых своя (§12).
		raise InvalidCharacterStateChange(
			"Эффект не может изменять один показатель дважды: " + ", ".join(duplicated)
		)

	core = [
		EffectModifier(
			instance_id=f"check:{index}",
			code=modifier.code,
			value=modifier.value,
			stacking=modifier.stacking,
			priority=modifier.priority,
		)
		for index, modifier in enumerate(modifiers)
	]

	try:
		combine_modifier(core)
	except ValueError as exc:
		raise InvalidCharacterStateChange(
			f"Изменения эффекта недействительны: {exc}"
		) from exc


def _change(
	owner: StateOwner,
	*,
	instance_id: UUID,
	reason_type: str,
	status_before: str | None,
	status_after: str,
	event_code: str | None = None,
	request_id: UUID | None = None,
	source_type: str | None = None,
	source_id: UUID | None = None,
	comment: str | None = None,
) -> EffectChange:
	return EffectChange(
		**_owner_columns(owner),
		instance_id=instance_id,
		reason_type=reason_type,
		status_before=status_before,
		status_after=status_after,
		event_code=event_code,
		request_id=request_id,
		source_type=source_type,
		source_id=source_id,
		comment=comment,
	)


def _read_instance(instance: EffectInstance) -> EffectInstanceRead:
	return EffectInstanceRead(
		id=instance.id,
		status=instance.status,
		effect_id=instance.effect_id,
		source_type=instance.source_type,
		source_id=instance.source_id,
		application_key=instance.application_key,
		duration_value=instance.duration_value,
		duration_unit=instance.duration_unit,
		started_event=instance.started_event,
		started_at=instance.started_at,
		ended_at=instance.ended_at,
	)


async def apply_effect(
	session: AsyncSession,
	owner: StateOwner,
	apply: EffectInstanceApplyIn,
) -> EffectInstanceRead:
	"""Наложить эффект на цель (§12).

	Повторная обработка того же события (тот же application_key)
	переиспользует экземпляр вместо создания копии. Экземпляр без ключа
	наложения — разовое наложение, оно не идемпотентно по определению.
	"""
	_require_clean_session(session)
	owner_id = _owner_key(owner)
	await _lock_owner(session, owner_id)
	_validate_modifiers(apply.modifiers)

	if apply.application_key is not None:
		existing = await _find_by_application_key(session, owner_id, apply.application_key)

		if existing is not None:
			# Копия не создаётся: повтор события меняет только данные
			# того же экземпляра и не порождает новую запись журнала.
			existing.modifiers = [modifier.model_dump() for modifier in apply.modifiers]
			existing.conditions = apply.conditions
			existing.duration_value = apply.duration_value
			existing.duration_unit = apply.duration_unit
			existing.end_events = apply.end_events

			if apply.started_event is not None:
				existing.started_event = apply.started_event

			await session.flush()
			return _read_instance(existing)

	instance = EffectInstance(
		**_owner_columns(owner),
		status="active",
		effect_id=apply.effect_id,
		source_type=apply.source_type,
		source_id=apply.source_id,
		application_key=apply.application_key,
		modifiers=[modifier.model_dump() for modifier in apply.modifiers],
		conditions=apply.conditions,
		duration_value=apply.duration_value,
		duration_unit=apply.duration_unit,
		end_events=apply.end_events,
		started_event=apply.started_event,
	)
	session.add(instance)
	await session.flush()

	session.add(
		_change(
			owner,
			instance_id=instance.id,
			reason_type="apply",
			status_before=None,
			status_after="active",
			event_code=apply.started_event,
			request_id=apply.application_key,
			source_type=apply.source_type,
			source_id=apply.source_id,
			comment=apply.comment,
		)
	)

	await session.flush()
	await session.refresh(instance)
	return _read_instance(instance)


async def _find_by_application_key(
	session: AsyncSession,
	owner_id: UUID,
	application_key: UUID,
) -> EffectInstance | None:
	return (
		await session.execute(
			select(EffectInstance).where(
				EffectInstance.owner_key == owner_id,
				EffectInstance.application_key == application_key,
			)
		)
	).scalar_one_or_none()


async def extend_effect(
	session: AsyncSession,
	owner: StateOwner,
	instance_id: UUID,
	extend: EffectExtendIn,
) -> EffectInstanceRead:
	"""Продлить длительность экземпляра (§12).

	Экземпляр без числовой длительности продлить нечего: отказ с
	диагностикой честнее молчаливого создания счётчика.
	"""
	_require_clean_session(session)
	owner_id = _owner_key(owner)
	await _lock_owner(session, owner_id)
	instance = await _load_instance(session, owner_id, instance_id)

	if instance.status == "withdrawn":
		raise InvalidCharacterStateChange("Снятый экземпляр эффекта не продлевается")

	if instance.duration_value is None:
		raise InvalidCharacterStateChange(
			f"Экземпляр {instance_id} не имеет длительности, продлевать нечего"
		)

	old_duration = instance.duration_value
	instance.duration_value = old_duration + extend.duration_delta

	session.add(
		_change(
			owner,
			instance_id=instance.id,
			reason_type="extend",
			status_before=instance.status,
			status_after=instance.status,
			comment=extend.comment,
		)
	)

	await session.flush()
	return _read_instance(instance)


async def suppress_effect(
	session: AsyncSession,
	owner: StateOwner,
	instance_id: UUID,
	*reasons: str,
) -> EffectInstanceRead:
	"""Подавить экземпляр (§12).

	Подавление снимает экземпляр со свёртки, но не удаляет его:
	возобновление возвращает действие эффекта без повторного наложения.
	"""
	_require_clean_session(session)
	owner_id = _owner_key(owner)
	await _lock_owner(session, owner_id)
	instance = await _load_instance(session, owner_id, instance_id)

	if instance.status == "withdrawn":
		raise InvalidCharacterStateChange("Снятый экземпляр не подавляется")

	if instance.status == "suppressed":
		# Повторное подавление не создаёт вторую запись в журнале (§12).
		return _read_instance(instance)

	old_status = instance.status
	instance.status = "suppressed"

	session.add(
		_change(
			owner,
			instance_id=instance.id,
			reason_type="suppress",
			status_before=old_status,
			status_after="suppressed",
			event_code=reasons[0] if reasons else None,
			comment=", ".join(reasons) or None,
		)
	)

	await session.flush()
	return _read_instance(instance)


async def resume_effect(
	session: AsyncSession,
	owner: StateOwner,
	instance_id: UUID,
	*reasons: str,
) -> EffectInstanceRead:
	"""Снять подавление, вернув экземпляр в действие (§12)."""
	_require_clean_session(session)
	owner_id = _owner_key(owner)
	await _lock_owner(session, owner_id)
	instance = await _load_instance(session, owner_id, instance_id)

	if instance.status == "withdrawn":
		raise InvalidCharacterStateChange("Снятый экземпляр не возобновляется")

	if instance.status == "active":
		return _read_instance(instance)

	instance.status = "active"

	# Причина возвращения действия фиксируется как наложение того же
	# экземпляра: журнал объясняет, почему эффект снова участвует в
	# свёртке (§12).
	session.add(
		_change(
			owner,
			instance_id=instance.id,
			reason_type="apply",
			status_before="suppressed",
			status_after="active",
			event_code=reasons[0] if reasons else None,
			comment=", ".join(reasons) or None,
		)
	)

	await session.flush()
	return _read_instance(instance)


async def withdraw_effect(
	session: AsyncSession,
	owner: StateOwner,
	instance_id: UUID,
	*reasons: str,
) -> EffectInstanceRead:
	"""Снять экземпляр эффекта (§12).

	Снятие адресует ровно один экземпляр по его идентичности, поэтому
	другие эффекты с тем же названием продолжают действовать.
	"""
	_require_clean_session(session)
	owner_id = _owner_key(owner)
	await _lock_owner(session, owner_id)
	instance = await _load_instance(session, owner_id, instance_id)

	if instance.status == "withdrawn":
		# Повтор обработки события снятия не создаёт вторую причину (§12).
		return _read_instance(instance)

	old_status = instance.status
	instance.status = "withdrawn"
	instance.ended_at = _now()

	session.add(
		_change(
			owner,
			instance_id=instance.id,
			reason_type="withdraw",
			status_before=old_status,
			status_after="withdrawn",
			event_code=reasons[0] if reasons else None,
			comment=", ".join(reasons) or None,
		)
	)

	await session.flush()
	return _read_instance(instance)


async def withdraw_by_source(
	session: AsyncSession,
	owner: StateOwner,
	source_type: str,
	source_id: UUID | None,
	*reasons: str,
) -> list[EffectInstanceRead]:
	"""Снять все экземпляры одного источника (§12).

	Снятие ограничено источником: экземпляры прочих источников
	остаются активными, совпадение названия роли не играет.
	"""
	_require_clean_session(session)
	owner_id = _owner_key(owner)
	await _lock_owner(session, owner_id)

	statement = (
		select(EffectInstance)
		.where(
			EffectInstance.owner_key == owner_id,
			EffectInstance.source_type == source_type,
			EffectInstance.source_id == source_id,
			EffectInstance.status != "withdrawn",
		)
		.order_by(EffectInstance.started_at, EffectInstance.id)
	)
	instances = list((await session.execute(statement)).scalars().all())

	removed: list[EffectInstanceRead] = []

	for instance in instances:
		old_status = instance.status
		instance.status = "withdrawn"
		instance.ended_at = _now()

		session.add(
			_change(
				owner,
				instance_id=instance.id,
				reason_type="withdraw",
				status_before=old_status,
				status_after="withdrawn",
				event_code=reasons[0] if reasons else None,
				source_type=source_type,
				source_id=source_id,
				comment=", ".join(reasons) or None,
			)
		)
		removed.append(_read_instance(instance))

	await session.flush()
	return removed


async def withdraw_by_event(
	session: AsyncSession,
	owner: StateOwner,
	event_code: str,
	*reasons: str,
) -> list[EffectInstanceRead]:
	"""Снять экземпляры, для которых переданное событие является прекращающим (§12).

	Событие прекращает эффект только если его код перечислен в
	end_events экземпляра: молчаливое снятие всего подряд недопустимо.
	"""
	_require_clean_session(session)
	owner_id = _owner_key(owner)
	await _lock_owner(session, owner_id)

	statement = (
		select(EffectInstance)
		.where(
			EffectInstance.owner_key == owner_id,
			EffectInstance.status != "withdrawn",
		)
		.order_by(EffectInstance.started_at, EffectInstance.id)
	)
	instances = list((await session.execute(statement)).scalars().all())

	removed: list[EffectInstanceRead] = []

	for instance in instances:
		if event_code not in (instance.end_events or []):
			continue

		old_status = instance.status
		instance.status = "withdrawn"
		instance.ended_at = _now()

		session.add(
			_change(
				owner,
				instance_id=instance.id,
				reason_type="withdraw",
				status_before=old_status,
				status_after="withdrawn",
				event_code=event_code,
				comment=", ".join(reasons) or None,
			)
		)
		removed.append(_read_instance(instance))

	await session.flush()
	return removed


async def read_effect_instances(
	session: AsyncSession,
	owner: StateOwner,
) -> EffectInstancesRead:
	"""Вернуть экземпляры владельца, включая снятые (§12)."""
	statement = (
		select(EffectInstance)
		.where(EffectInstance.owner_key == _owner_key(owner))
		.order_by(EffectInstance.started_at, EffectInstance.id)
	)
	instances = (await session.execute(statement)).scalars().all()

	return EffectInstancesRead(items=[_read_instance(instance) for instance in instances])


async def aggregate_effects(
	session: AsyncSession,
	owner: StateOwner,
) -> EffectAggregationRead:
	"""Свернуть активные экземпляры цели по показателям (§12).

	В свёртке участвуют только активные экземпляры: подавленный и
	снятый не влияют на итог. Идентичность экземпляра попадает в ядро
	как instance_id, поэтому совпадение кода или названия разные
	экземпляры не объединяет.
	"""
	statement = (
		select(EffectInstance)
		.where(
			EffectInstance.owner_key == _owner_key(owner),
			EffectInstance.status == "active",
		)
		.order_by(EffectInstance.started_at, EffectInstance.id)
	)
	instances = list((await session.execute(statement)).scalars().all())

	# Один экземпляр может менять несколько показателей: модификатор
	# берётся по коду показателя, а не «первый попавшийся».
	by_code: dict[str, list[tuple[EffectInstance, dict]]] = {}

	for instance in instances:
		for modifier in instance.modifiers or []:
			by_code.setdefault(modifier["code"], []).append((instance, modifier))

	items: list[EffectAggregateRead] = []

	for code in sorted(by_code):
		entries = by_code[code]
		core = [
			EffectModifier(
				instance_id=str(instance.id),
				code=code,
				value=modifier["value"],
				stacking=modifier.get("stacking", "stacking"),
				priority=modifier.get("priority", 0),
			)
			for instance, modifier in entries
		]
		stacking_by_id = {
			str(instance.id): modifier.get("stacking", "stacking")
			for instance, modifier in entries
		}

		try:
			total, outcomes = combine_modifier(core)
		except ValueError as exc:
			raise InvalidCharacterStateChange(
				f"Свёртка эффектов по показателю {code} недействительна: {exc}"
			) from exc

		items.append(
			EffectAggregateRead(
				code=code,
				total=total,
				outcomes=[
					EffectOutcomeRead(
						instance_id=UUID(outcome.instance_id),
						code=outcome.code,
						value=outcome.value,
						stacking=stacking_by_id[outcome.instance_id],
						result=outcome.result,
					)
					for outcome in outcomes
				],
			)
		)

	return EffectAggregationRead(items=items)


async def list_effect_changes(
	session: AsyncSession,
	owner: StateOwner,
) -> EffectChangesRead:
	"""Вернуть журнал причин владельца в хронологическом порядке (§12)."""
	statement = (
		select(EffectChange)
		.where(EffectChange.owner_key == _owner_key(owner))
		.order_by(EffectChange.created_at, EffectChange.id)
	)
	changes = (await session.execute(statement)).scalars().all()

	items = [
		EffectChangeRead(
			id=change.id,
			instance_id=change.instance_id,
			reason_type=change.reason_type,
			status_before=change.status_before,
			status_after=change.status_after,
			event_code=change.event_code,
			request_id=change.request_id,
			source_type=change.source_type,
			source_id=change.source_id,
			comment=change.comment,
			created_at=change.created_at,
		)
		for change in changes
	]

	return EffectChangesRead(items=items)


__all__ = [
	"apply_effect",
	"extend_effect",
	"suppress_effect",
	"resume_effect",
	"withdraw_effect",
	"withdraw_by_source",
	"withdraw_by_event",
	"read_effect_instances",
	"aggregate_effects",
	"list_effect_changes",
]
