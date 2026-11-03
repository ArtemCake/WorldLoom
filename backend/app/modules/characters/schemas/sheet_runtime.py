# backend/app/modules/characters/schemas/sheet_runtime.py

"""Прежние боевые поля листа и независимый признак его активности."""

from __future__ import annotations
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator


class SheetRuntimeModel(BaseModel):
	model_config = ConfigDict(from_attributes=True, extra="forbid")

class LegacySheetRead(SheetRuntimeModel):
	id: UUID
	revision: int = Field(ge=1)
	hp_current: int | None
	hp_temp: int | None
	death_save_successes: int | None
	death_save_failures: int | None
	conditions: list[str] | dict[str, JsonValue] | None
	spell_slots_json: dict[str, dict[str, int]] | None
	is_active_in_game: bool

class LegacySheetUpdate(SheetRuntimeModel):
	expected_revision: int = Field(ge=1)
	hp_current: int | None = Field(default=None, ge=0, le=2147483647)
	hp_temp: int | None = Field(default=None, ge=0, le=2147483647)
	death_save_successes: int | None = Field(default=None, ge=0, le=3)
	death_save_failures: int | None = Field(default=None, ge=0, le=3)
	conditions: list[str] | dict[str, JsonValue] | None = None
	is_active_in_game: bool | None = None

	@field_validator("hp_current", "hp_temp", "death_save_successes", "death_save_failures", "is_active_in_game", mode="before")
	@classmethod
	def reject_explicit_null(cls, value: object) -> object:
		if value is None:
			raise ValueError("Поле не может иметь значение null.")

		return value

class SpellSlotsUpdate(SheetRuntimeModel):
	expected_revision: int = Field(ge=1)
	slots: dict[str, dict[str, int]]

class SheetActivityUpdate(SheetRuntimeModel):
	expected_revision: int = Field(ge=1)
	is_active_in_game: bool

class SheetActivityRead(SheetRuntimeModel):
	id: UUID
	revision: int = Field(ge=1)
	is_active_in_game: bool