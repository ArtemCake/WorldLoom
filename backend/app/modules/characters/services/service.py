# backend/app/modules/characters/services/service.py

"""Чтение и изменение универсального состояния персонажей.

Управление транзакцией принадлежит вызывающему коду.
Функции не выполняют commit() и rollback().

Для операций нужна сессия без ожидающих ORM-изменений.
Блокировки удерживаются до завершения внешней транзакции.
"""

from __future__ import annotations
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import lazyload
from sqlalchemy.orm.exc import StaleDataError
from backend.app.modules.characters.errors import (CharacterAccessDenied, CharacterNotFound, CharacterStateConflict,
	CharacterStateNotInitialized, CharacterStateStorageError, InvalidCharacterStateChange)
from backend.app.modules.characters.models import (Character, CharacterSheet)
from backend.app.modules.characters.schemas.schemas import (CharacterCreate, CharacterDelete, CharacterListQuery, CharacterListRead, CharacterMetadataUpdate, CharacterRead,
	CharacterSheetCreate, CharacterSheetRead, CharacterStateRead, CharacterStateUpdate, CharacterSummary)
from backend.app.modules.game_systems.models.game_systems import (GameSystemRulesVersion, GameSystem)
from backend.app.modules.game_systems.rules.rules_engine import (apply_sheet_changes, create_sheet_state, evaluate_sheet_state, validate_rules_profile)
from backend.app.modules.game_systems.schemas.game_rules import (RulesProfile, SheetState)
from backend.app.modules.game_systems.schemas.rule_calculations import (AttributePreviewResult)
from backend.app.modules.games.models.lobby import Game, Party


StateOwner = Character | CharacterSheet

def _require_clean_session(session: AsyncSession) -> None:
	"""Не перезагружать ORM-объекты поверх несохранённых изменений."""
	if session.new or session.dirty or session.deleted:
		raise RuntimeError(
			"Операция состояния требует сессии "
			"без ожидающих ORM-изменений"
		)

async def _get_character(session: AsyncSession, character_id: UUID, user_id: UUID, *, for_update: bool) -> Character:
	statement = (
		select(Character)
		.where(
			Character.id == character_id,
			Character.user_id == user_id,
			)
		.options(lazyload("*"))
		.execution_options(populate_existing=True)
		.with_for_update(read=not for_update)
	)

	character = (
		await session.execute(statement)
	).scalar_one_or_none()

	if character is None:
		raise CharacterNotFound("Персонаж не найден")

	return character

async def _get_sheet(session: AsyncSession, sheet_id: UUID, user_id: UUID, *, for_update: bool, require_rules: bool = True) -> CharacterSheet:
	"""Проверить доступ и закрепление правил.

	Порядок блокировок: игра, участие, лист.
	Обновление листа дополнительно защищено его ORM-ревизией.
	"""
	game_id = await session.scalar(
		select(CharacterSheet.game_id).where(
			CharacterSheet.id == sheet_id,
			CharacterSheet.player_id == user_id,
			)
	)

	if game_id is None:
		raise CharacterNotFound("Лист персонажа не найден")

	game = (
		await session.execute(
			select(
				Game.id,
				Game.system_id,
				Game.rules_version_id,
			)
			.where(Game.id == game_id)
			.with_for_update(read=True)
		)
	).one_or_none()

	if game is None:
		raise CharacterNotFound("Игра не найдена")

	memberships = (
		await session.execute(
			select(
				Party.id,
				Party.is_active,
				Party.role_in_game,
			)
			.where(
				Party.game_id == game_id,
				Party.user_id == user_id,
				)
			.with_for_update(read=True)
		)
	).all()

	# Не выбирать произвольное участие при дублирующих записях.
	if len(memberships) != 1:
		raise CharacterAccessDenied(
			"Не удалось подтвердить участие в игре"
		)

	membership = memberships[0]

	if not membership.is_active or membership.role_in_game == "banned":
		raise CharacterAccessDenied(
			"Вы не являетесь активным участником игры"
		)

	sheet = (
		await session.execute(
			select(CharacterSheet)
			.where(
				CharacterSheet.id == sheet_id,
				CharacterSheet.player_id == user_id,
				CharacterSheet.game_id == game_id,
				)
			.options(lazyload("*"))
			.execution_options(populate_existing=True)
			.with_for_update(read=not for_update)
		)
	).scalar_one_or_none()

	if sheet is None:
		raise CharacterNotFound("Лист персонажа не найден")

	if game.rules_version_id is None:
		raise CharacterStateConflict(
			"За игрой не закреплена публикация правил"
		)

	if (
			sheet.state_rules_version_id is not None
			and sheet.state_rules_version_id != game.rules_version_id
	):
		raise CharacterStateConflict(
			"Состояние листа относится к другой публикации правил"
		)

	if sheet.state_rules_version_id is not None:
		publication_system_id = await session.scalar(
			select(GameSystemRulesVersion.system_id).where(
				GameSystemRulesVersion.id
				== sheet.state_rules_version_id
			)
		)

		if publication_system_id != game.system_id:
			raise CharacterStateStorageError(
				"Публикация листа не соответствует системе игры"
			)

	return sheet

async def _load_state(session: AsyncSession, owner: StateOwner) -> tuple[RulesProfile, SheetState, AttributePreviewResult]:
	"""Загрузить закреплённый профиль и проверить сохранённое состояние."""
	version_id = owner.state_rules_version_id
	raw_state = owner.state_json

	if version_id is None and raw_state is None:
		raise CharacterStateNotInitialized(
			"Запись ещё не переведена на универсальное состояние"
		)

	if version_id is None or raw_state is None:
		raise CharacterStateStorageError(
			"Нарушена привязка состояния к публикации правил"
		)

	version = (
		await session.execute(
			select(GameSystemRulesVersion)
			.where(GameSystemRulesVersion.id == version_id)
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
		profile = RulesProfile.model_validate(version.rules_json)
		state = SheetState.model_validate(raw_state)
		result = evaluate_sheet_state(profile, state)
	except ValueError as exc:
		raise CharacterStateStorageError(
			"Сохранённое состояние или формат публикации "
			"не поддерживается числовым исполнителем"
		) from exc

	return profile, state, result

def _check_expected(owner: StateOwner, data: CharacterStateUpdate) -> None:
	if owner.revision != data.expected_revision:
		raise CharacterStateConflict(
			"Запись уже изменена. Получите актуальное состояние"
		)

	if (
			owner.state_rules_version_id
			!= data.expected_rules_version_id
	):
		raise CharacterStateConflict(
			"Закреплённая публикация правил изменилась"
		)

def _make_response(owner: StateOwner, state: SheetState, result: AttributePreviewResult) -> CharacterStateRead:
	return CharacterStateRead(
		id=owner.id,
		revision=owner.revision,
		rules_version_id=owner.state_rules_version_id,
		state=state,
		derived=dict(result.derived),
	)

async def _read_state(session: AsyncSession, owner: StateOwner) -> CharacterStateRead:
	_, state, result = await _load_state(session, owner)
	return _make_response(owner, state, result)

async def _update_state(session: AsyncSession, owner: StateOwner, data: CharacterStateUpdate) -> CharacterStateRead:
	_check_expected(owner, data)

	profile, state, result = await _load_state(session, owner)

	try:
		updated = apply_sheet_changes(
			profile,
			state,
			data.changes,
		)
		updated_result = evaluate_sheet_state(profile, updated)
	except ValueError as exc:
		raise InvalidCharacterStateChange(
			"Изменение не соответствует закреплённым правилам: "
			f"{exc}"
		) from exc

	# Повторная запись тех же значений не увеличивает ревизию.
	if updated == state:
		return _make_response(owner, state, result)

	# JSONB изменяем заменой словаря, а не вложенным присваиванием.
	owner.state_json = updated.model_dump(mode="json")

	try:
		await session.flush()
	except StaleDataError as exc:
		# После неудачного flush внешняя транзакция
		# должна быть отменена вызывающим кодом.
		raise CharacterStateConflict(
			"Запись была изменена другой операцией"
		) from exc

	return _make_response(owner, updated, updated_result)

async def get_character_state(session: AsyncSession, character_id: UUID, user_id: UUID) -> CharacterStateRead:
	_require_clean_session(session)

	character = await _get_character(
		session,
		character_id,
		user_id,
		for_update=False,
	)
	return await _read_state(session, character)

async def update_character_state(session: AsyncSession, character_id: UUID, user_id: UUID, data: CharacterStateUpdate) -> CharacterStateRead:
	data = CharacterStateUpdate.model_validate(data)
	_require_clean_session(session)

	character = await _get_character(
		session,
		character_id,
		user_id,
		for_update=True,
	)
	return await _update_state(session, character, data)

async def get_character_sheet_state(session: AsyncSession, sheet_id: UUID, user_id: UUID) -> CharacterStateRead:
	_require_clean_session(session)

	sheet = await _get_sheet(
		session,
		sheet_id,
		user_id,
		for_update=False,
	)
	return await _read_state(session, sheet)

async def update_character_sheet_state(session: AsyncSession, sheet_id: UUID, user_id: UUID, data: CharacterStateUpdate) -> CharacterStateRead:
	data = CharacterStateUpdate.model_validate(data)
	_require_clean_session(session)

	sheet = await _get_sheet(
		session,
		sheet_id,
		user_id,
		for_update=True,
	)
	return await _update_state(session, sheet, data)

async def create_character(session: AsyncSession, user_id: UUID, data: CharacterCreate) -> CharacterRead:
	"""Создать собственный шаблон по выбранной публикации.

	Не выполняет commit. Вызывающий код завершает транзакцию.
	"""
	data = CharacterCreate.model_validate(data)
	_require_clean_session(session)

	# Определяем систему выбранной публикации.
	# Затем блокируем систему и саму публикацию до конца транзакции.
	system_id = await session.scalar(
		select(GameSystemRulesVersion.system_id).where(
			GameSystemRulesVersion.id == data.rules_version_id
		)
	)

	if system_id is None:
		raise CharacterNotFound("Публикация правил не найдена")

	system = (
		await session.execute(
			select(
				GameSystem.id,
				GameSystem.is_active,
			)
			.where(GameSystem.id == system_id)
			.with_for_update(read=True)
		)
	).one_or_none()

	if system is None or not system.is_active:
		raise CharacterAccessDenied(
			"Система недоступна для создания персонажей"
		)

	version = (
		await session.execute(
			select(GameSystemRulesVersion)
			.where(
				GameSystemRulesVersion.id == data.rules_version_id,
				GameSystemRulesVersion.system_id == system_id,
				)
			.options(lazyload("*"))
			.execution_options(populate_existing=True)
			.with_for_update(read=True)
		)
	).scalar_one_or_none()

	if version is None:
		raise CharacterNotFound("Публикация правил не найдена")

	try:
		profile = RulesProfile.model_validate(version.rules_json)
		profile = validate_rules_profile(profile)
	except ValueError as exc:
		raise CharacterStateStorageError(
			"Публикация не поддерживается числовым исполнителем "
			"или содержит некорректное начальное состояние"
		) from exc

	try:
		state = create_sheet_state(
			profile,
			changes=data.initial_changes,
		)
		result = evaluate_sheet_state(profile, state)
	except ValueError as exc:
		raise InvalidCharacterStateChange(
			"Начальные значения не соответствуют правилам: "
			f"{exc}"
		) from exc

	character = Character(
		user_id=user_id,
		name=data.name,
		state_json=state.model_dump(mode="json"),
		state_rules_version_id=version.id,
		revision=1,
	)

	session.add(character)
	await session.flush()

	return CharacterRead(
		id=character.id,
		user_id=character.user_id,
		name=character.name,
		calculated_state=_make_response(
			character,
			state,
			result,
		),
	)

async def create_character_sheet(session: AsyncSession, user_id: UUID, data: CharacterSheetCreate) -> CharacterSheetRead:
	"""Создать игровой лист копированием собственного шаблона.

	Правила игры и шаблона должны ссылаться на одну публикацию.
	Инвентарь, заклинания и прежние поля не копируются.
	"""
	data = CharacterSheetCreate.model_validate(data)
	_require_clean_session(session)

	# Порядок блокировок: игра, участие, шаблон, публикация.
	game = (
		await session.execute(
			select(
				Game.id,
				Game.system_id,
				Game.rules_version_id,
			)
			.where(Game.id == data.game_id)
			.with_for_update(read=True)
		)
	).one_or_none()

	if game is None:
		raise CharacterNotFound("Игра не найдена")

	memberships = (
		await session.execute(
			select(
				Party.id,
				Party.is_active,
				Party.role_in_game,
			)
			.where(
				Party.game_id == data.game_id,
				Party.user_id == user_id,
				)
			.with_for_update(read=True)
		)
	).all()

	if len(memberships) != 1:
		raise CharacterAccessDenied(
			"Не удалось подтвердить участие в игре"
		)

	membership = memberships[0]

	if not membership.is_active or membership.role_in_game == "banned":
		raise CharacterAccessDenied(
			"Вы не являетесь активным участником игры"
		)

	if (
			game.rules_version_id is None
			or game.rules_version_id != data.expected_rules_version_id
	):
		raise CharacterStateConflict(
			"Закреплённая публикация игры отсутствует "
			"или отличается от ожидаемой"
		)

	character = await _get_character(
		session,
		data.character_id,
		user_id,
		for_update=False,
	)

	if character.revision != data.expected_character_revision:
		raise CharacterStateConflict(
			"Шаблон уже изменён. Получите его актуальное состояние"
		)

	if (
			character.state_rules_version_id
			!= data.expected_rules_version_id
	):
		raise CharacterStateConflict(
			"Шаблон и игра используют разные публикации правил "
			"или шаблон ещё не переведён на новый формат"
		)

	profile, source_state, _ = await _load_state(
		session,
		character,
	)

	publication_system_id = await session.scalar(
		select(GameSystemRulesVersion.system_id).where(
			GameSystemRulesVersion.id
			== character.state_rules_version_id
		)
	)

	if publication_system_id != game.system_id:
		raise CharacterStateStorageError(
			"Публикация не соответствует системе игры"
		)

	# Создаём отдельное дерево данных, а не общую ссылку
	# на словарь исходного шаблона.
	copied_state = SheetState.model_validate(
		source_state.model_dump(mode="json")
	)
	result = evaluate_sheet_state(profile, copied_state)

	sheet = CharacterSheet(
		player_id=user_id,
		game_id=game.id,
		base_character_id=character.id,
		party_id=membership.id,
		version_note=data.version_note,
		state_json=copied_state.model_dump(mode="json"),
		state_rules_version_id=game.rules_version_id,
		revision=1,
		is_active_in_game=True,
	)

	session.add(sheet)
	await session.flush()

	return CharacterSheetRead(
		id=sheet.id,
		player_id=sheet.player_id,
		game_id=sheet.game_id,
		base_character_id=sheet.base_character_id,
		party_id=sheet.party_id,
		version_note=sheet.version_note,
		is_active_in_game=sheet.is_active_in_game,
		calculated_state=_make_response(
			sheet,
			copied_state,
			result,
		),
	)

def _make_character_summary(character: Character) -> CharacterSummary:
	"""Собрать метаданные без разбора и вычисления state_json."""
	return CharacterSummary(
		id=character.id,
		user_id=character.user_id,
		name=character.name,
		revision=character.revision,
		rules_version_id=character.state_rules_version_id,
		has_stored_state=character.state_json is not None,
	)

async def list_characters(session: AsyncSession, user_id: UUID, query: CharacterListQuery | None = None) -> CharacterListRead:
	"""Вернуть страницу собственных шаблонов без расчёта состояния.

	Выбираются только поля краткой карточки.
	Дополнительная строка определяет наличие следующей страницы.
	"""
	query = CharacterListQuery.model_validate(
		query if query is not None else {}
	)
	_require_clean_session(session)

	statement = (
		select(
			Character.id,
			Character.user_id,
			Character.name,
			Character.revision,
			Character.state_rules_version_id.label(
				"rules_version_id"
			),
			Character.state_json.is_not(None).label(
				"has_stored_state"
			),
		)
		.where(Character.user_id == user_id)
		.order_by(
			Character.created_at.desc(),
			Character.id.desc(),
		)
		.offset(query.offset)
		.limit(query.limit + 1)
	)

	rows = (
		await session.execute(statement)
	).mappings().all()

	has_next = len(rows) > query.limit

	items = [
		CharacterSummary.model_validate(dict(row))
		for row in rows[:query.limit]
	]

	return CharacterListRead(
		items=items,
		next_offset=(
			query.offset + query.limit
			if has_next
			else None
		),
	)

async def get_character(session: AsyncSession, character_id: UUID, user_id: UUID) -> CharacterRead:
	"""Прочитать собственный шаблон и вычислить его состояние."""
	_require_clean_session(session)

	character = await _get_character(
		session,
		character_id,
		user_id,
		for_update=False,
	)
	calculated_state = await _read_state(
		session,
		character,
	)

	return CharacterRead(
		id=character.id,
		user_id=character.user_id,
		name=character.name,
		calculated_state=calculated_state,
	)

async def get_character_sheet(session: AsyncSession, sheet_id: UUID, user_id: UUID) -> CharacterSheetRead:
	"""Прочитать собственный лист с проверкой участия и правил игры."""
	_require_clean_session(session)

	sheet = await _get_sheet(
		session,
		sheet_id,
		user_id,
		for_update=False,
	)
	calculated_state = await _read_state(
		session,
		sheet,
	)

	return CharacterSheetRead(
		id=sheet.id,
		player_id=sheet.player_id,
		game_id=sheet.game_id,
		base_character_id=sheet.base_character_id,
		party_id=sheet.party_id,
		version_note=sheet.version_note,
		is_active_in_game=sheet.is_active_in_game,
		calculated_state=calculated_state,
	)

async def update_character_metadata(session: AsyncSession, character_id: UUID, user_id: UUID, data: CharacterMetadataUpdate) -> CharacterSummary:
	"""Переименовать собственный шаблон с проверкой ревизии.

	Работает и для записей без универсального состояния.
	Игровые значения и публикация правил не изменяются.
	"""
	data = CharacterMetadataUpdate.model_validate(data)
	_require_clean_session(session)

	character = await _get_character(
		session,
		character_id,
		user_id,
		for_update=True,
	)

	if character.revision != data.expected_revision:
		raise CharacterStateConflict(
			"Запись уже изменена. Получите актуальную карточку"
		)

	if character.name == data.name:
		return _make_character_summary(character)

	character.name = data.name

	try:
		await session.flush()
	except StaleDataError as exc:
		raise CharacterStateConflict(
			"Запись была изменена другой операцией"
		) from exc

	return _make_character_summary(character)

async def delete_character(session: AsyncSession, character_id: UUID, user_id: UUID, data: CharacterDelete) -> None:
	"""Удалить собственный шаблон, сохранив игровые листы.

	Ожидается ранее согласованная настройка:
	- Character.sheets без delete и delete-orphan;
	- CharacterSheet.base_character_id с ON DELETE SET NULL.

	Не требует разбора игрового состояния.
	Не выполняет commit или rollback.
	"""
	data = CharacterDelete.model_validate(data)
	_require_clean_session(session)

	character = await _get_character(
		session,
		character_id,
		user_id,
		for_update=True,
	)

	if character.revision != data.expected_revision:
		raise CharacterStateConflict(
			"Запись уже изменена. Получите актуальную карточку"
		)

	await session.delete(character)

	try:
		await session.flush()
	except StaleDataError as exc:
		raise CharacterStateConflict(
			"Запись была изменена или удалена другой операцией"
		) from exc