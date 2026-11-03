# backend/app/modules/maps/schemas.py

from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict, model_validator
from datetime import datetime


class MapGridSettings(BaseModel):
	rows: int = Field(default=20, ge=1, le=200)
	cols: int = Field(default=20, ge=1, le=200)
	show_grid: bool = True

class MapCreate(BaseModel):
	game_id: UUID
	session_id: UUID | None = None
	title: str = Field(max_length=255)
	map_type: str
	background_image_url: str | None = Field(default=None, max_length=1000)
	grid_settings_json: dict | None = None
	fog_of_war_enabled: bool = True
	lighting_model: str = "basic"

class MapUpdate(BaseModel):
	title: str | None = Field(default=None, max_length=255)
	background_image_url: str | None = Field(default=None, max_length=1000)
	grid_settings_json: dict | None = None
	fog_of_war_enabled: bool | None = None
	lighting_model: str | None = None

class HexGridGenerateIn(BaseModel):
	rows: int = Field(gt=0, le=200)
	cols: int = Field(gt=0, le=200)

class MapRead(BaseModel):
	model_config = ConfigDict(from_attributes=True)

	id: UUID
	game_id: UUID
	session_id: UUID | None
	title: str
	map_type: str
	background_image_url: str | None
	grid_settings_json: dict
	fog_of_war_enabled: bool
	lighting_model: str
	is_active_in_session: bool
	created_at: datetime
	updated_at: datetime

class MapLayerRead(BaseModel):
	model_config = ConfigDict(from_attributes=True)

	id: UUID
	map_id: UUID
	name: str
	layer_type: str
	z_index: int

class MapGameTargetIn(BaseModel):
	model_config = ConfigDict(extra="forbid")

	source_game_id: UUID
	target_game_id: UUID

class MapVisibilitySettings(BaseModel):
	model_config = ConfigDict(extra="forbid")

	line_of_sight: bool = True
	use_elevation: bool = True
	blocker_key: str = Field(default="cover", min_length=1, max_length=100)

class MapPreviewIn(BaseModel):
	game_id: UUID
	map_id: UUID | None = None
	rows: int = Field(default=20, ge=1, le=200)
	cols: int = Field(default=20, ge=1, le=200)
	origin_q: int | None = None
	origin_r: int | None = None
	vision_radius: int = Field(default=6, ge=0, le=50)
	visibility: MapVisibilitySettings | None = None

	@model_validator(mode="after")
	def validate_origin(self):
		if (self.origin_q is None) != (self.origin_r is None):
			raise ValueError("Нужны обе координаты наблюдателя")

		return self

class FogOfWarRecalcIn(BaseModel):
	viewer_token_ids: list[UUID]

class FogOfWarRecalcOut(BaseModel):
	visible_hex_ids: list[UUID]

class MapDeletionRead(BaseModel):
	map_id: UUID
	deleted: bool
	cleanup_complete: bool