# backend/app/modules/characters/schemas/selection_schemas.py

"""Контракты выборов контента и происхождения свойств (Этап E)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SheetSelectionModel(BaseModel):
	model_config = ConfigDict(from_attributes=True, extra="forbid")


# ---------- выбор контента (§9, §13) ----------


class ContentSelectionIn(SheetSelectionModel):
	"""Запрос на выбор элемента каталога персонажем."""

	source_type: str = Field(
		min_length=1,
		max_length=30,
		pattern=r"^[a-z][a-z0-9_]*$",
	)
	source_id: UUID


class ContentSelectionRead(SheetSelectionModel):
	"""Чтение активного выбора."""

	id: UUID
	character_id: UUID
	source_type: str
	source_id: UUID
	is_active: bool
	applied_at: datetime


class ContentSelectionsRead(SheetSelectionModel):
	"""Пакет активных выборов."""

	items: list[ContentSelectionRead]


# ---------- гранты и происхождение (§9, §14.1) ----------


class ContentGrantIn(SheetSelectionModel):
	"""Грант — выданное свойство с указанием способа влияния.

	mode "add": к текущему значению добавляется amount.
	mode "set": текущее значение заменяется на previous_value.
	"""

	code: str = Field(
		min_length=1,
		max_length=100,
		pattern=r"^[a-z][a-z0-9_]*$",
	)
	source_type: str = Field(
		min_length=1,
		max_length=30,
		pattern=r"^[a-z][a-z0-9_]*$",
	)
	source_id: UUID | None = None
	mode: str = Field(default="add", pattern=r"^(add|set)$")
	amount: int = Field(default=0)
	previous_value: int = Field(default=0)


class ContentGrantRead(SheetSelectionModel):
	"""Чтение применённого гранта."""

	id: UUID
	code: str
	source_type: str
	source_id: UUID | None
	mode: str
	amount: int
	previous_value: int


class ContentWithdrawalRead(SheetSelectionModel):
	"""Чтение отозванного гранта."""

	code: str
	source_type: str
	amount: int
	previous_value: int
	mode: str


class ProvenanceRead(SheetSelectionModel):
	"""Полное происхождение свойства."""

	id: UUID
	code: str
	source_type: str
	source_id: UUID | None
	mode: str
	amount: int
	previous_value: int
