# backend/app/modules/characters/schemas/schemas.py

"""Контракты универсального числового состояния персонажей."""

from __future__ import annotations
from pydantic import Field
from backend.app.modules.game_systems.schemas.game_rules import RulesModel, SheetState, SheetStateChanges, TransportUUID
from backend.app.modules.game_systems.schemas.rules.rule_calculations import CalculationValue, Code

class CharacterStateUpdate(RulesModel):
	"""Замена части исходных значений без смены правил."""

	expected_revision: int = Field(ge=1)
	expected_rules_version_id: TransportUUID
	changes: SheetStateChanges

class CharacterStateRead(RulesModel):
	"""Проверенное состояние шаблона или игрового листа."""

	id: TransportUUID
	revision: int = Field(ge=1)
	rules_version_id: TransportUUID
	state: SheetState
	derived: dict[Code, CalculationValue]

class CharacterCreate(RulesModel):
	"""Создание собственного шаблона по опубликованным правилам.

	Если initial_changes отсутствует, используются начальные
	значения профиля. Переданный профиль от клиента не принимается.
	"""

	name: str = Field(min_length=1, max_length=100, pattern=r"\S")
	rules_version_id: TransportUUID
	initial_changes: SheetStateChanges | None = None

class CharacterSheetCreate(RulesModel):
	"""Копирование собственного шаблона в конкретную игру.

	Ожидаемые ревизия и публикация защищают от создания
	по незаметно изменившимся исходным данным.
	"""

	character_id: TransportUUID
	game_id: TransportUUID
	expected_character_revision: int = Field(ge=1)
	expected_rules_version_id: TransportUUID
	version_note: str | None = Field(default=None, max_length=200)

class CharacterRead(RulesModel):
	"""Шаблон без прежних системно-зависимых полей."""

	id: TransportUUID
	user_id: TransportUUID
	name: str
	calculated_state: CharacterStateRead

class CharacterSheetRead(RulesModel):
	"""Игровой лист с независимым состоянием."""

	id: TransportUUID
	player_id: TransportUUID
	game_id: TransportUUID
	base_character_id: TransportUUID | None
	party_id: TransportUUID | None
	version_note: str | None
	is_active_in_game: bool
	calculated_state: CharacterStateRead

class CharacterSummary(RulesModel):
	"""Краткая карточка без вычисления игрового состояния.

	has_stored_state означает только наличие state_json.
	Это не подтверждение корректности сохранённого состояния.
	"""

	id: TransportUUID
	user_id: TransportUUID
	name: str
	revision: int = Field(ge=1)
	rules_version_id: TransportUUID | None
	has_stored_state: bool

class CharacterListQuery(RulesModel):
	"""Параметры страницы списка собственных шаблонов."""

	limit: int = Field(default=50, ge=1, le=100)
	offset: int = Field(default=0, ge=0)

class CharacterListRead(RulesModel):
	items: list[CharacterSummary]
	next_offset: int | None

class CharacterMetadataUpdate(RulesModel):
	"""Изменение имени без изменения игровых значений."""

	expected_revision: int = Field(ge=1)
	name: str = Field(min_length=1, max_length=100, pattern=r"\S")

class CharacterDelete(RulesModel):
	"""Условие удаления собственного шаблона."""

	expected_revision: int = Field(ge=1)