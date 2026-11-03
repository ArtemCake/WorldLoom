# backend/app/modules/characters/schemas/content_schemas.py

"""Запросы и ответы для заклинаний и инвентаря игрового листа."""

from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator


class SheetContentModel(BaseModel):
	model_config = ConfigDict(from_attributes=True, extra="forbid")

class SpellOnSheetIn(SheetContentModel):
	spell_id: UUID
	is_known: bool = True
	is_prepared: bool = False

class SpellOnSheetUpdate(SheetContentModel):
	is_known: bool | None = None
	is_prepared: bool | None = None

	@field_validator("is_known", "is_prepared", mode="before")
	@classmethod
	def reject_explicit_null(cls, value):
		if value is None:
			raise ValueError("Поле не может иметь значение null.")

		return value

class SpellOnSheetRead(SheetContentModel):
	id: UUID
	spell_id: UUID
	is_known: bool
	is_prepared: bool

class InventoryItemIn(SheetContentModel):
	item_id: UUID
	quantity: int = Field(default=1, ge=1, le=2147483647)
	custom_name: str | None = Field(default=None, max_length=255)

class InventoryItemUpdate(SheetContentModel):
	quantity: int | None = Field(default=None, ge=1, le=2147483647)
	is_attuned: bool | None = None
	is_equipped: bool | None = None
	equipped_slot: str | None = Field(default=None, max_length=30)
	ammo_count: int | None = Field(default=None, ge=0, le=2147483647)
	charges_current: int | None = Field(default=None, ge=0, le=2147483647)
	custom_name: str | None = Field(default=None, max_length=255)
	notes_json: dict[str, JsonValue] | None = None

	@field_validator("quantity", "is_attuned", "is_equipped", mode="before")
	@classmethod
	def reject_explicit_null(cls, value):
		if value is None:
			raise ValueError("Поле не может иметь значение null.")

		return value

class InventoryItemRead(SheetContentModel):
	sheet_id: UUID
	item_id: UUID
	quantity: int
	is_attuned: bool
	is_equipped: bool
	equipped_slot: str | None
	ammo_count: int | None
	charges_current: int | None
	custom_name: str | None
	notes_json: dict[str, JsonValue] | None