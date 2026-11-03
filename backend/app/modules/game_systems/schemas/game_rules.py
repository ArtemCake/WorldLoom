# backend/app/modules/game_systems/schemas/game_rules.py

"""Профиль пользовательских вычислений и числовое состояние листа.

Не содержит правил конкретной игровой системы.
Старые профили не преобразуются в новый формат автоматически.
"""

from __future__ import annotations
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID
from pydantic import ConfigDict, Field, model_validator
from backend.app.modules.game_systems.schemas.rule_calculations import (AttributeCalculations, CalculationModel, CalculationValue, Code, MAX_ATTRIBUTES)


# UUID в HTTP-запросах передаётся строкой.
# Остальные поля моделей сохраняют строгую проверку типов.
TransportUUID = Annotated[UUID, Field(strict=False)]


class RulesModel(CalculationModel):
	"""Общие настройки контрактов правил."""

class RulesProfile(RulesModel):
	"""Числовые определения и начальные значения листа.

	Версии 1 и 2 относились к прежнему системно-зависимому
	контракту. Их нельзя интерпретировать как новый профиль.
	"""

	schema_version: Literal[3]

	calculations: AttributeCalculations

	initial_attributes: dict[Code, CalculationValue] = Field(
		max_length=MAX_ATTRIBUTES,
	)

	@model_validator(mode="after")
	def validate_initial_attributes(self):
		definitions = self.calculations.attributes

		expected = set(definitions)
		received = set(self.initial_attributes)

		missing = sorted(expected - received)
		unknown = sorted(received - expected)

		problems: list[str] = []

		if missing:
			problems.append(
				"не заданы начальные значения: "
				+ ", ".join(missing)
			)

		if unknown:
			problems.append(
				"неизвестные начальные показатели: "
				+ ", ".join(unknown)
			)

		if problems:
			raise ValueError("; ".join(problems))

		for code, definition in definitions.items():
			value = self.initial_attributes[code]

			if not definition.min_value <= value <= definition.max_value:
				raise ValueError(
					f"Начальное значение {code}: "
					f"допустимый диапазон от {definition.min_value} "
					f"до {definition.max_value}"
				)

		return self

class SheetState(RulesModel):
	"""Числовое состояние листа без вычисляемых значений.

	Связь с игрой, владельцем и публикацией правил
	устанавливается моделями и сервисами, а не этим словарём.
	"""

	schema_version: Literal[1] = 1

	attributes: dict[Code, CalculationValue] = Field(
		max_length=MAX_ATTRIBUTES,
	)

class SheetStateChanges(RulesModel):
	"""Частичное изменение исходных числовых значений.

	Переданные значения заменяют прежние.
	Это не приращения и не операции расходования ресурсов.
	"""

	attributes: dict[Code, CalculationValue] = Field(
		min_length=1,
		max_length=MAX_ATTRIBUTES,
	)

# Контракты управления черновиками и публикациями.
# Подключение к сервисам выполняется отдельным пакетом.
class GameSystemRulesDraftCreate(RulesModel):
	rules: RulesProfile

class GameSystemRulesDraftUpdate(RulesModel):
	expected_revision: int = Field(ge=1)
	rules: RulesProfile

class GameSystemRulesPublish(RulesModel):
	expected_revision: int = Field(ge=1)

class GameRulesVersionBind(RulesModel):
	rules_version_id: TransportUUID

	# null означает ожидание отсутствующей закреплённой версии.
	expected_rules_version_id: TransportUUID | None = Field(...)

class GameSystemRulesDraftRead(RulesModel):
	model_config = ConfigDict(
		from_attributes=True,
		populate_by_name=True,
	)

	id: TransportUUID
	system_id: TransportUUID
	revision: int = Field(ge=1)

	engine_version_id: TransportUUID | None = None

	rules_overrides: dict[str, Any] | None = Field(
		default=None,
		validation_alias="rules_overrides_json",
	)
	rules: RulesProfile = Field(
		validation_alias="rules_json",
	)

	created_at: datetime
	updated_at: datetime

class GameSystemRulesDraftState(RulesModel):
	draft: GameSystemRulesDraftRead | None

class GameSystemRulesVersionRead(RulesModel):
	model_config = ConfigDict(
		from_attributes=True,
		populate_by_name=True,
	)

	id: TransportUUID
	system_id: TransportUUID
	version_number: int = Field(ge=1)

	engine_version_id: TransportUUID | None = None

	rules_overrides: dict[str, Any] | None = Field(
		default=None,
		validation_alias="rules_overrides_json",
	)
	rules: RulesProfile = Field(
		validation_alias="rules_json",
	)

	rules_engine_version: str
	published_at: datetime

class GameSystemRulesPublishedState(RulesModel):
	version: GameSystemRulesVersionRead | None