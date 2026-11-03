# backend/app/modules/games/schemas/game_state.py

"""Контракты токенов и ручного управления очередью игрового стола."""

from __future__ import annotations
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


DB_INT_MIN = -(2 ** 31)
DB_INT_MAX = 2 ** 31 - 1

class TokenCreate(BaseModel):
	model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

	session_id: UUID
	current_map_id: UUID | None = None
	character_sheet_id: UUID | None = None
	npc_id: UUID | None = None
	image_url: str = Field(min_length=1, max_length=1000)
	display_name: str | None = Field(default=None, max_length=100)
	grid_x: int = Field(ge=DB_INT_MIN, le=DB_INT_MAX)
	grid_y: int = Field(ge=DB_INT_MIN, le=DB_INT_MAX)
	elevation: int = Field(default=0, ge=DB_INT_MIN, le=DB_INT_MAX)
	rotation_deg: float = 0.0
	hp_current: int = Field(ge=DB_INT_MIN, le=DB_INT_MAX)
	hp_max: int = Field(ge=DB_INT_MIN, le=DB_INT_MAX)
	conditions_json: dict[str, JsonValue] | None = None
	is_visible_to_players: bool = True
	controlled_by_ids: list[UUID] | None = None
	vision_radius_cells: int = Field(ge=0, le=DB_INT_MAX)

class TokenUpdate(BaseModel):
	model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

	current_map_id: UUID | None = None
	character_sheet_id: UUID | None = None
	npc_id: UUID | None = None
	image_url: str | None = Field(default=None, min_length=1, max_length=1000)
	display_name: str | None = Field(default=None, max_length=100)
	elevation: int | None = Field(default=None, ge=DB_INT_MIN, le=DB_INT_MAX)
	rotation_deg: float | None = None
	hp_current: int | None = Field(default=None, ge=DB_INT_MIN, le=DB_INT_MAX)
	hp_max: int | None = Field(default=None, ge=DB_INT_MIN, le=DB_INT_MAX)
	conditions_json: dict[str, JsonValue] | None = None
	is_visible_to_players: bool | None = None
	controlled_by_ids: list[UUID] | None = None
	vision_radius_cells: int | None = Field(default=None, ge=0, le=DB_INT_MAX)

	@model_validator(mode="after")
	def reject_required_nulls(self) -> TokenUpdate:
		required = ("image_url", "elevation", "rotation_deg", "hp_current", "hp_max", "is_visible_to_players", "vision_radius_cells")

		for name in required:
			if name in self.model_fields_set and getattr(self, name) is None:
				raise ValueError(f"Поле {name} не может быть null")

		return self

class TokenMove(BaseModel):
	model_config = ConfigDict(extra="forbid")

	grid_x: int = Field(ge=DB_INT_MIN, le=DB_INT_MAX)
	grid_y: int = Field(ge=DB_INT_MIN, le=DB_INT_MAX)
	hex_id: UUID | None = None

class TokenRead(BaseModel):
	model_config = ConfigDict(from_attributes=True, allow_inf_nan=False)

	id: UUID
	session_id: UUID
	current_map_id: UUID | None
	character_sheet_id: UUID | None
	npc_id: UUID | None
	owner_id: UUID
	image_url: str
	display_name: str | None
	grid_x: int
	grid_y: int
	current_hex_id: UUID | None
	vision_radius_cells: int
	elevation: int
	rotation_deg: float
	hp_current: int
	hp_max: int
	conditions_json: dict[str, JsonValue] | None
	is_visible_to_players: bool
	controlled_by_ids: list[UUID] | None
	created_at: datetime
	updated_at: datetime

class TurnOrderCreate(BaseModel):
	"""Готовый порядок; сервис не рассчитывает и не сортирует инициативу."""

	model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

	entries: list[dict[str, JsonValue]] = Field(min_length=1, max_length=1000)