# backend/app/modules/game_systems/schemas/game_system_versions.py

"""Контракты раздельных текстовых правил, механики и комплекта системы.

Игровая система разделяется на два независимых версионируемых блока:
- текстовые правила (rulebook: главы и поля без формул);
- механика (исполняемый числовой профиль без текстового раздела).

Опубликованная версия системы (комплект) связывает версию правил и
версию механики. Механика обязательна, текстовая версия необязательна.
"""

from __future__ import annotations
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID
from pydantic import ConfigDict, Field, model_validator
from backend.app.modules.game_systems.schemas.rules.rule_calculations import (
    AttributeCalculations,
    CalculationModel,
    CalculationValue,
    Code,
    MAX_ATTRIBUTES,
)
from backend.app.modules.game_systems.schemas.rules.rule_resources import (
    MAX_RESOURCES,
    ResourceDefinition,
)
from backend.app.modules.game_systems.schemas.rules.rulebook import RulebookChapter
from backend.app.modules.game_systems.schemas.game_rules import RulesProfile


# UUID в HTTP-запросах передаётся строкой.
TransportUUID = Annotated[UUID, Field(strict=False)]

MAX_TEXT_CHAPTERS = 64


class SystemTextContent(CalculationModel):
	"""Текстовые правила системы: главы без формул и ресурсов."""

	schema_version: Literal[1] = 1

	chapters: dict[Code, RulebookChapter] = Field(
		default_factory=dict,
		max_length=MAX_TEXT_CHAPTERS,
	)


class SystemMechanicContent(CalculationModel):
	"""Исполняемая механика: расчёты, начальные значения и ресурсы.

	Текстового раздела здесь нет. Это числовая основа листа,
	по которой работает серверный исполнитель формул.
	"""

	schema_version: Literal[1] = 1

	calculations: AttributeCalculations

	initial_attributes: dict[Code, CalculationValue] = Field(
		max_length=MAX_ATTRIBUTES,
	)

	resources: dict[Code, ResourceDefinition] = Field(
		default_factory=dict,
		max_length=MAX_RESOURCES,
	)

	@model_validator(mode="after")
	def validate_resource_references(self):
		namespaces = {
			"attribute": self.calculations.attributes,
			"stat": self.calculations.derived,
		}

		for code, definition in self.resources.items():
			if type(definition.maximum) is int:
				continue

			namespace, target = definition.maximum.split(".", 1)

			if target not in namespaces[namespace]:
				raise ValueError(
					f"Ресурс {code}: неизвестная ссылка максимума {definition.maximum}"
				)

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


# --------------------------------------------------------------------------- #
# Черновик текстовых правил.
# --------------------------------------------------------------------------- #

class GameSystemTextDraftCreate(CalculationModel):
	text: SystemTextContent


class GameSystemTextDraftUpdate(CalculationModel):
	expected_revision: int = Field(ge=1)
	text: SystemTextContent


class GameSystemTextDraftRead(CalculationModel):
	model_config = ConfigDict(
		from_attributes=True,
		populate_by_name=True,
		extra="forbid",
		strict=True,
		validate_default=True,
		revalidate_instances="always",
	)

	id: TransportUUID
	system_id: TransportUUID
	revision: int = Field(ge=1)
	is_published: bool

	text: SystemTextContent = Field(validation_alias="text_json")

	created_at: datetime
	updated_at: datetime


class GameSystemTextDraftState(CalculationModel):
	draft: GameSystemTextDraftRead | None


# --------------------------------------------------------------------------- #
# Опубликованная версия текстовых правил.
# --------------------------------------------------------------------------- #

class GameSystemTextPublish(CalculationModel):
	expected_revision: int = Field(ge=1)


class GameSystemTextVersionRead(CalculationModel):
	model_config = ConfigDict(
		from_attributes=True,
		populate_by_name=True,
		extra="forbid",
		strict=True,
		validate_default=True,
		revalidate_instances="always",
	)

	id: TransportUUID
	system_id: TransportUUID
	version_number: int = Field(ge=1)
	source_draft_revision: int = Field(ge=1)

	text: SystemTextContent = Field(validation_alias="text_json")

	published_at: datetime


# --------------------------------------------------------------------------- #
# Черновик механики.
# --------------------------------------------------------------------------- #

class GameSystemMechanicDraftCreate(CalculationModel):
	mechanic: SystemMechanicContent


class GameSystemMechanicDraftUpdate(CalculationModel):
	expected_revision: int = Field(ge=1)
	mechanic: SystemMechanicContent


class GameSystemMechanicOriginSet(CalculationModel):
	"""Привязка черновика механики к опубликованной версии движка."""

	engine_version_id: TransportUUID


class GameSystemMechanicDraftRead(CalculationModel):
	model_config = ConfigDict(
		from_attributes=True,
		populate_by_name=True,
		extra="forbid",
		strict=True,
		validate_default=True,
		revalidate_instances="always",
	)

	id: TransportUUID
	system_id: TransportUUID
	revision: int = Field(ge=1)
	is_published: bool

	engine_version_id: TransportUUID | None = None

	mechanic_overrides: dict[str, object] | None = Field(
		default=None,
		validation_alias="mechanic_overrides_json",
	)
	mechanic: SystemMechanicContent = Field(validation_alias="mechanic_json")

	created_at: datetime
	updated_at: datetime


class GameSystemMechanicDraftState(CalculationModel):
	draft: GameSystemMechanicDraftRead | None


# --------------------------------------------------------------------------- #
# Опубликованная версия механики.
# --------------------------------------------------------------------------- #

class GameSystemMechanicPublish(CalculationModel):
	expected_revision: int = Field(ge=1)


class GameSystemMechanicVersionRead(CalculationModel):
	model_config = ConfigDict(
		from_attributes=True,
		populate_by_name=True,
		extra="forbid",
		strict=True,
		validate_default=True,
		revalidate_instances="always",
	)

	id: TransportUUID
	system_id: TransportUUID
	version_number: int = Field(ge=1)
	source_draft_revision: int = Field(ge=1)
	engine_version_id: TransportUUID | None = None
	rules_engine_version: str

	mechanic_overrides: dict[str, object] | None = Field(
		default=None,
		validation_alias="mechanic_overrides_json",
	)
	mechanic: SystemMechanicContent = Field(validation_alias="mechanic_json")

	published_at: datetime


# --------------------------------------------------------------------------- #
# Комплект: опубликованная версия системы = правила + механика.
# --------------------------------------------------------------------------- #

class GameSystemVersionPublish(CalculationModel):
	"""Собрать версию системы из актуальных черновиков правил и механики.

	Номера исходных ревизий обязательны: публикация комплекта не должна
	молча использовать состояние, изменившееся во время операции.
	"""

	expected_text_revision: int | None = Field(default=None, ge=1)
	expected_mechanic_revision: int = Field(ge=1)


class GameSystemVersionRead(CalculationModel):
	model_config = ConfigDict(
		from_attributes=True,
		populate_by_name=True,
		extra="forbid",
		strict=True,
		validate_default=True,
		revalidate_instances="always",
	)

	id: TransportUUID
	system_id: TransportUUID
	version_number: int = Field(ge=1)
	text_version_id: TransportUUID | None = None
	mechanic_version_id: TransportUUID
	published_at: datetime


class GameSystemVersionSummary(CalculationModel):
	"""Элемент истории комплектов.

	Версия программного исполнителя берётся из составной версии механики:
	комплект не задаёт её самостоятельно, а наследует числовую основу.
	"""

	id: TransportUUID
	system_id: TransportUUID
	version_number: int = Field(ge=1)
	text_version_id: TransportUUID | None = None
	mechanic_version_id: TransportUUID
	rules_engine_version: str
	published_at: datetime


class GameSystemVersionPage(CalculationModel):
	items: list[GameSystemVersionSummary]
	next_before: int | None = Field(default=None, ge=1)


class GameSystemTextVersionPage(CalculationModel):
	"""Страница опубликованных версий текстовых правил."""

	items: list[GameSystemTextVersionRead]
	next_before: int | None = Field(default=None, ge=1)


class GameSystemMechanicVersionPage(CalculationModel):
	"""Страница опубликованных версий механики."""

	items: list[GameSystemMechanicVersionRead]
	next_before: int | None = Field(default=None, ge=1)


class GameSystemTextPublishedState(CalculationModel):
	"""Последняя опубликованная версия текстовых правил."""

	version: GameSystemTextVersionRead | None


class GameSystemMechanicPublishedState(CalculationModel):
	"""Последняя опубликованная версия механики."""

	version: GameSystemMechanicVersionRead | None


class GameSystemVersionBind(CalculationModel):
	"""Закрепление текущей версии системы (комплекта)."""

	version_id: TransportUUID

	# null означает ожидание отсутствующей закреплённой версии.
	expected_version_id: TransportUUID | None = Field(...)


class GameSystemCurrentVersionState(CalculationModel):
	version: GameSystemVersionRead | None


class GameSystemPublishedDocument(CalculationModel):
	"""Комплект вместе с собранным документом правил.

	Модель чтения: числовая основа берётся из версии механики,
	текстовые главы — из версии правил. Профиль передаётся в формате,
	который понимают редактор книги и серверный исполнитель формул.
	"""

	version: GameSystemVersionRead
	rules: RulesProfile
	rules_engine_version: str


class GameSystemPublishedDocumentState(CalculationModel):
	"""Собранный документ опубликованной версии системы."""

	document: GameSystemPublishedDocument | None


__all__ = [
	"SystemTextContent",
	"SystemMechanicContent",
	"GameSystemTextDraftCreate",
	"GameSystemTextDraftUpdate",
	"GameSystemTextDraftRead",
	"GameSystemTextDraftState",
	"GameSystemTextPublish",
	"GameSystemTextVersionRead",
	"GameSystemMechanicDraftCreate",
	"GameSystemMechanicDraftUpdate",
	"GameSystemMechanicOriginSet",
	"GameSystemMechanicDraftRead",
	"GameSystemMechanicDraftState",
	"GameSystemMechanicPublish",
	"GameSystemMechanicVersionRead",
	"GameSystemVersionPublish",
	"GameSystemVersionRead",
	"GameSystemVersionSummary",
	"GameSystemVersionPage",
	"GameSystemTextVersionPage",
	"GameSystemMechanicVersionPage",
	"GameSystemTextPublishedState",
	"GameSystemMechanicPublishedState",
	"GameSystemVersionBind",
	"GameSystemCurrentVersionState",
	"GameSystemPublishedDocument",
	"GameSystemPublishedDocumentState",
]
