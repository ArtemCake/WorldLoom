# backend/app/modules/characters/services/resource_service.py

"""Хранение значений ресурсов и журнал причин (Этап F2, §10).

Значения ресурсов занимают отдельную таблицу sheet_resource_values:
сохранённое состояние допускает только показатели, поэтому второй
источник правды в state_json невозможен (§30#2). Текущий запас —
единственное число, которое здесь хранится; максимум вычисляет
существующее ядро по закреплённой публикации правил.

Разделение ответственности (§1.2):
- resource_engine / resource_policy — чистые вычисления; сервис их
  переиспользует и не дублирует;
- сервис — единственный путь записи значений и журнала;
- транзакция принадлежит вызывающему коду: commit/rollback нет.

Защита от двойного списания (§27-F): перед изменением строки запасов
владельца блокируются SELECT ... FOR UPDATE, поэтому одновременные
действия согласовываются на уровне БД, а независимые ресурсы не
снимаются вместе.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import lazyload

from backend.app.modules.characters.errors import (
	CharacterNotFound,
	CharacterStateNotInitialized,
	CharacterStateStorageError,
	InvalidCharacterStateChange,
)
from backend.app.modules.characters.models import (
	Character,
	CharacterSheet,
	SheetResourceChange,
	SheetResourceValue,
)
from backend.app.modules.characters.schemas.resource_schemas import (
	ResourceChangeRead,
	ResourceChangesRead,
	ResourceValueRead,
	ResourceValuesRead,
)
from backend.app.modules.game_systems.models.system_versions import GameSystemMechanicVersion
from backend.app.modules.game_systems.rules.mechanic_codec import mechanic_to_profile
from backend.app.modules.game_systems.rules import resource_engine
from backend.app.modules.game_systems.rules.resource_policy import (
	ResourceLimitPolicy,
	apply_limit_policy,
)
from backend.app.modules.game_systems.schemas.game_rules import RulesProfile, SheetState
from backend.app.modules.game_systems.schemas.rules.rule_resources import (
	ResourceAmounts,
	ResourceDefinitions,
	ResourceState,
)

StateOwner = Character | CharacterSheet


def _require_clean_session(session: AsyncSession) -> None:
	"""Не блокировать строки поверх несохранённых ORM-изменений."""
	if session.new or session.dirty or session.deleted:
		raise RuntimeError(
			"Операция ресурсов требует сессии без ожидающих ORM-изменений"
		)


def _owner_key(owner: StateOwner) -> UUID:
	"""Идентификатор владельца запасов: лист или собственный шаблон."""
	if isinstance(owner, (CharacterSheet, Character)):
		return owner.id

	raise TypeError(f"Неподдерживаемый владелец ресурсов: {type(owner).__name__}")


def _owner_columns(owner: StateOwner) -> dict[str, UUID | None]:
	"""Распределить владельца по колонкам внешнего ключа (§14.1)."""
	if isinstance(owner, CharacterSheet):
		return {"character_sheet_id": owner.id, "character_id": None}

	return {"character_sheet_id": None, "character_id": owner.id}


def _definitions(profile: RulesProfile) -> ResourceDefinitions:
	"""Собрать определения ресурсов из закреплённого профиля."""
	return ResourceDefinitions(resources=dict(profile.resources))


async def _load_rules(session: AsyncSession, owner: StateOwner) -> tuple[RulesProfile, SheetState]:
	"""Загрузить закреплённый профиль и состояние для вычисления максимумов.

	Публикация правил фиксируется общей блокировкой, чтобы максимумы не
	поплыли от перевыпуска прямо посреди операции со значениями.
	"""
	version_id = owner.state_rules_version_id
	raw_state = owner.state_json

	if version_id is None or raw_state is None:
		raise CharacterStateNotInitialized(
			"Ресурсы требуют закреплённой публикации правил и состояния"
		)

	version = (
		await session.execute(
			select(GameSystemMechanicVersion)
			.where(GameSystemMechanicVersion.id == version_id)
			.options(lazyload("*"))
			.execution_options(populate_existing=True)
			.with_for_update(read=True)
		)
	).scalar_one_or_none()

	if version is None:
		raise CharacterStateStorageError(
			"Закреплённая публикация правил не найдена"
		)

	try:
		profile = RulesProfile.model_validate(mechanic_to_profile(version.mechanic_json))
		state = SheetState.model_validate(raw_state)
	except ValueError as exc:
		raise CharacterStateStorageError(
			"Сохранённое состояние или формат публикации не поддерживается"
		) from exc

	return profile, state


async def _load_values(
	session: AsyncSession,
	owner_id: UUID,
	*,
	for_update: bool,
) -> tuple[dict[str, int], list[SheetResourceValue]]:
	"""Прочитать текущие запасы владельца, при необходимости заблокировав их."""
	statement = (
		select(SheetResourceValue)
		.where(SheetResourceValue.owner_key == owner_id)
		.order_by(SheetResourceValue.code)
	)

	if for_update:
		statement = statement.with_for_update()

	rows = list((await session.execute(statement)).scalars().all())

	return {row.code: row.value for row in rows}, rows


def _new_value(owner: StateOwner, code: str, value: int) -> SheetResourceValue:
	return SheetResourceValue(**_owner_columns(owner), code=code, value=value)


def _new_change(
	owner: StateOwner,
	*,
	code: str,
	reason_type: str,
	previous_value: int,
	value: int,
	delta: int,
	maximum: int | None,
	event_code: str | None,
	source_type: str | None,
	source_id: UUID | None,
	comment: str | None,
) -> SheetResourceChange:
	return SheetResourceChange(
		**_owner_columns(owner),
		code=code,
		reason_type=reason_type,
		previous_value=previous_value,
		value=value,
		delta=delta,
		maximum=maximum,
		event_code=event_code,
		source_type=source_type,
		source_id=source_id,
		comment=comment,
	)


async def _commit_state(
	session: AsyncSession,
	owner: StateOwner,
	*,
	rows: list[SheetResourceValue],
	before: dict[str, int],
	after: ResourceState,
	profile: RulesProfile,
	sheet: SheetState,
	definitions: ResourceDefinitions,
	reason_type: str,
	event_code: str | None = None,
	source_type: str | None = None,
	source_id: UUID | None = None,
	comment: str | None = None,
) -> ResourceState:
	"""Записать изменившиеся запасы и причину каждого изменения.

	Дельта считается от заблокированного снимка before, поэтому две
	одновременные транзакции не спишут одно и то же дважды (§27-F).
	Изменение с нулевой дельтой в журнал не попадает, кроме init, где
	создание запаса фиксируется даже при нулевом начальном значении.
	"""
	maximums = resource_engine.resolve_resource_limits(profile, sheet, definitions)
	by_code = {row.code: row for row in rows}

	for code in sorted(after.values):
		previous_value = before.get(code, 0)
		value = after.values[code]
		delta = value - previous_value

		if delta == 0 and reason_type != "init":
			continue

		if code in by_code:
			by_code[code].value = value
		else:
			session.add(_new_value(owner, code, value))

		session.add(
			_new_change(
				owner,
				code=code,
				reason_type=reason_type,
				previous_value=previous_value,
				value=value,
				delta=delta,
				maximum=maximums.get(code),
				event_code=event_code,
				source_type=source_type,
				source_id=source_id,
				comment=comment,
			)
		)

	await session.flush()
	return after


async def init_resources(
	session: AsyncSession,
	owner: StateOwner,
	*,
	comment: str | None = None,
) -> ResourceState:
	"""Создать запасы по начальным значениям (§10).

	Операция идемпотентна: существующие ресурсы не перезаписываются,
	создаются только отсутствующие. Повторный вызов не дублирует
	начальное заполнение (§27-E).
	"""
	_require_clean_session(session)
	owner_id = _owner_key(owner)
	profile, sheet = await _load_rules(session, owner)
	definitions = _definitions(profile)
	before, rows = await _load_values(session, owner_id, for_update=True)

	if set(before) == set(definitions.resources):
		return ResourceState(values=before)

	try:
		fresh = resource_engine.create_resource_state(profile, sheet, definitions)
	except ValueError as exc:
		raise InvalidCharacterStateChange(
			f"Начальные значения ресурсов недействительны: {exc}"
		) from exc

	missing = {code: fresh.values[code] for code in fresh.values if code not in before}

	return await _commit_state(
		session,
		owner,
		rows=rows,
		before=before,
		after=ResourceState(values=missing),
		profile=profile,
		sheet=sheet,
		definitions=definitions,
		reason_type="init",
		comment=comment,
	)


async def spend_resources(
	session: AsyncSession,
	owner: StateOwner,
	amounts: dict[str, int],
	*,
	source_type: str | None = None,
	source_id: UUID | None = None,
	comment: str | None = None,
) -> ResourceState:
	"""Списать ресурсы по стоимости действия (§10).

	Недостаточный запас отклоняется ядром до записи: значение и журнал
	остаются прежними, двойного списания не происходит (§27-F).
	"""
	_require_clean_session(session)
	owner_id = _owner_key(owner)
	profile, sheet = await _load_rules(session, owner)
	definitions = _definitions(profile)
	before, rows = await _load_values(session, owner_id, for_update=True)

	try:
		updated = resource_engine.spend_resources(
			profile,
			sheet,
			definitions,
			ResourceState(values=before),
			ResourceAmounts(amounts=dict(amounts)),
		)
	except ValueError as exc:
		raise InvalidCharacterStateChange(
			f"Списание ресурсов отклонено: {exc}"
		) from exc

	return await _commit_state(
		session,
		owner,
		rows=rows,
		before=before,
		after=updated,
		profile=profile,
		sheet=sheet,
		definitions=definitions,
		reason_type="spend",
		source_type=source_type,
		source_id=source_id,
		comment=comment,
	)


async def restore_resources(
	session: AsyncSession,
	owner: StateOwner,
	amounts: dict[str, int],
	*,
	source_type: str | None = None,
	source_id: UUID | None = None,
	comment: str | None = None,
) -> ResourceState:
	"""Восстановить заданное количество, не превышая максимум (§10)."""
	_require_clean_session(session)
	owner_id = _owner_key(owner)
	profile, sheet = await _load_rules(session, owner)
	definitions = _definitions(profile)
	before, rows = await _load_values(session, owner_id, for_update=True)

	try:
		updated = resource_engine.restore_resources(
			profile,
			sheet,
			definitions,
			ResourceState(values=before),
			ResourceAmounts(amounts=dict(amounts)),
		)
	except ValueError as exc:
		raise InvalidCharacterStateChange(
			f"Восстановление ресурсов отклонено: {exc}"
		) from exc

	return await _commit_state(
		session,
		owner,
		rows=rows,
		before=before,
		after=updated,
		profile=profile,
		sheet=sheet,
		definitions=definitions,
		reason_type="restore",
		source_type=source_type,
		source_id=source_id,
		comment=comment,
	)


async def recover_resources(
	session: AsyncSession,
	owner: StateOwner,
	event: str,
	*,
	comment: str | None = None,
) -> ResourceState:
	"""Применить восстановление по подтверждённому событию (§10).

	Условия наступления события проверяет вызывающая процедура; здесь
	только сами запасы и журнал с кодом события.
	"""
	_require_clean_session(session)
	owner_id = _owner_key(owner)
	profile, sheet = await _load_rules(session, owner)
	definitions = _definitions(profile)
	before, rows = await _load_values(session, owner_id, for_update=True)

	try:
		updated = resource_engine.recover_resources(
			profile,
			sheet,
			definitions,
			ResourceState(values=before),
			event,
		)
	except ValueError as exc:
		raise InvalidCharacterStateChange(
			f"Событие восстановления отклонено: {exc}"
		) from exc

	return await _commit_state(
		session,
		owner,
		rows=rows,
		before=before,
		after=updated,
		profile=profile,
		sheet=sheet,
		definitions=definitions,
		reason_type="recover",
		event_code=event,
		comment=comment,
	)


async def apply_resource_limits(
	session: AsyncSession,
	owner: StateOwner,
	policy: ResourceLimitPolicy,
	*,
	comment: str | None = None,
) -> ResourceState:
	"""Ограничить запасы политикой после смены максимума (§10).

	Максимумы вычисляет ядро по действующей публикации. Прежние
	максимумы намеренно не хранятся (см. решение §30#2), поэтому в
	журнале предыдущий максимум приравнивается к прежнему запасу.
	"""
	_require_clean_session(session)
	owner_id = _owner_key(owner)
	profile, sheet = await _load_rules(session, owner)
	definitions = _definitions(profile)
	before, rows = await _load_values(session, owner_id, for_update=True)

	if not before:
		raise CharacterStateNotInitialized(
			"Запасы ещё не созданы, применять политику ограничения не к чему"
		)

	maximums = resource_engine.resolve_resource_limits(profile, sheet, definitions)

	try:
		adjusted, adjustments = apply_limit_policy(
			definitions,
			{},
			ResourceState(values=before),
			maximums,
			policy,
		)
	except ValueError as exc:
		raise InvalidCharacterStateChange(
			f"Политика ограничения применена некорректно: {exc}"
		) from exc

	by_code = {row.code: row for row in rows}

	for adjustment in adjustments:
		if adjustment.code in by_code:
			by_code[adjustment.code].value = adjustment.value

		session.add(
			_new_change(
				owner,
				code=adjustment.code,
				reason_type="limit",
				previous_value=adjustment.previous_value,
				value=adjustment.value,
				delta=adjustment.value - adjustment.previous_value,
				maximum=adjustment.maximum,
				event_code=None,
				source_type=None,
				source_id=None,
				comment=comment,
			)
		)

	await session.flush()
	return adjusted


async def set_resource_value(
	session: AsyncSession,
	owner: StateOwner,
	code: str,
	value: int,
	*,
	comment: str | None = None,
) -> ResourceState:
	"""Разрешённая ручная правка запаса (§10).

	Значение проверяется против вычисленного максимума: абсолютная
	правка не может создать второй источник правды о границе ресурса.
	"""
	_require_clean_session(session)
	owner_id = _owner_key(owner)
	profile, sheet = await _load_rules(session, owner)
	definitions = _definitions(profile)

	if code not in definitions.resources:
		raise InvalidCharacterStateChange(f"Неизвестный ресурс: {code}")

	before, rows = await _load_values(session, owner_id, for_update=True)
	maximums = resource_engine.resolve_resource_limits(profile, sheet, definitions)
	maximum = maximums[code]

	if not 0 <= value <= maximum:
		raise InvalidCharacterStateChange(
			f"Ресурс {code}: значение {value} вне диапазона 0..{maximum}"
		)

	return await _commit_state(
		session,
		owner,
		rows=rows,
		before=before,
		after=ResourceState(values={**before, code: value}),
		profile=profile,
		sheet=sheet,
		definitions=definitions,
		reason_type="manual",
		comment=comment,
	)


async def read_resources(
	session: AsyncSession,
	owner: StateOwner,
) -> ResourceValuesRead:
	"""Вернуть текущие запасы вместе с вычисленными максимумами (§10).

	Чтение не блокирует строки: максимум приходит из ядра, запас — из
	таблицы, второго источника правды нет.
	"""
	profile, sheet = await _load_rules(session, owner)
	definitions = _definitions(profile)
	values, _ = await _load_values(session, _owner_key(owner), for_update=False)
	maximums = resource_engine.resolve_resource_limits(profile, sheet, definitions)

	items = [
		ResourceValueRead(code=code, value=values[code], maximum=maximums[code])
		for code in sorted(values)
	]

	return ResourceValuesRead(items=items)


async def list_resource_changes(
	session: AsyncSession,
	owner: StateOwner,
) -> ResourceChangesRead:
	"""Вернуть журнал причин владельца в хронологическом порядке (§10)."""
	statement = (
		select(SheetResourceChange)
		.where(SheetResourceChange.owner_key == _owner_key(owner))
		.order_by(SheetResourceChange.created_at, SheetResourceChange.id)
	)
	rows = (await session.execute(statement)).scalars().all()

	return ResourceChangesRead(items=[ResourceChangeRead.model_validate(row) for row in rows])


__all__ = [
	"init_resources",
	"spend_resources",
	"restore_resources",
	"recover_resources",
	"apply_resource_limits",
	"set_resource_value",
	"read_resources",
	"list_resource_changes",
]
