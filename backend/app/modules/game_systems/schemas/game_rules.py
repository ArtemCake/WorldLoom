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
from backend.app.modules.game_systems.schemas.rules.rule_calculations import AttributeCalculations, CalculationModel
from backend.app.modules.game_systems.schemas.rules.rule_calculations import CalculationValue, Code, MAX_ATTRIBUTES
from backend.app.modules.game_systems.schemas.rules.rule_resources import MAX_RESOURCES, ResourceDefinition


# UUID в HTTP-запросах передаётся строкой.
# Остальные поля моделей сохраняют строгую проверку типов.
TransportUUID = Annotated[UUID, Field(strict=False)]


class RulesModel(CalculationModel):
	"""Общие настройки контрактов правил."""

class RulesProfile(RulesModel):
	"""Определения правил и начальных значений.

    Версия 3: числовой профиль без ресурсов.
    Версия 4: числовой профиль с явно переданным разделом ресурсов.

    Текущие запасы конкретного листа сюда не входят.
    """

	schema_version: Literal[3, 4]

	calculations: AttributeCalculations

	initial_attributes: dict[Code, CalculationValue] = Field(max_length=MAX_ATTRIBUTES)

	resources: dict[Code, ResourceDefinition] = Field(default_factory=dict, max_length=MAX_RESOURCES)

	@model_validator(mode="after")
	def validate_resource_contract(self):
		if self.schema_version == 3 and self.resources:
			raise ValueError("Ресурсы поддерживаются начиная с версии профиля 4")

		if self.schema_version == 4 and "resources" not in self.model_fields_set:
			raise ValueError("Для версии профиля 4 раздел resources нужно передать явно")

		namespaces = {
			"attribute": self.calculations.attributes,
			"stat": self.calculations.derived,
		}

		for code, definition in self.resources.items():
			if type(definition.maximum) is int:
				continue

			namespace, target = definition.maximum.split(".", 1)

			if target not in namespaces[namespace]:
				raise ValueError(f"Ресурс {code}: неизвестная ссылка максимума {definition.maximum}")

		return self

	@model_validator(mode="after")
	def validate_initial_attributes(self):
		definitions = self.calculations.attributes

		expected = set(definitions)
		received = set(self.initial_attributes)

		missing = sorted(expected - received)
		unknown = sorted(received - expected)

		problems: list[str] = []

		if missing:
			problems.append("не заданы начальные значения: " + ", ".join(missing))

		if unknown:
			problems.append("неизвестные начальные показатели: " + ", ".join(unknown))

		if problems:
			raise ValueError("; ".join(problems))

		for code, definition in definitions.items():
			value = self.initial_attributes[code]

			try:
				definition.validate_value(value)
			except ValueError as error:
				raise ValueError(f"Начальное значение {code}: {error}") from error

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

class GameSystemRulesVersionSummary(RulesModel):
	id: TransportUUID
	system_id: TransportUUID
	version_number: int = Field(ge=1)
	rules_engine_version: str
	published_at: datetime

class GameSystemRulesVersionPage(RulesModel):
	items: list[GameSystemRulesVersionSummary]
	next_before: int | None = Field(default=None, ge=1)