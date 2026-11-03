# backend/app/modules/catalog/schemas.py

"""Контракты чтения, создания и изменения карточек игровых систем."""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator


class GameSystemRead(BaseModel):
	model_config = ConfigDict(from_attributes=True)

	id: UUID
	name: str
	slug: str
	description: str | None = None

class GameSystemAdminRead(GameSystemRead):
	rules_engine_version: str
	is_active: bool
	created_at: datetime
	updated_at: datetime

class GameSystemCreate(BaseModel):
	model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

	name: str = Field(min_length=1, max_length=100)
	slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")
	description: str | None = None
	rules_engine_version: str = Field(default="1.0", min_length=1, max_length=20)
	is_active: bool = Field(default=True, strict=True)

class GameSystemUpdate(BaseModel):
	model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

	name: str | None = Field(default=None, min_length=1, max_length=100)
	slug: str | None = Field(default=None, min_length=1, max_length=100, pattern=r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")
	description: str | None = None
	rules_engine_version: str | None = Field(default=None, min_length=1, max_length=20)
	is_active: bool | None = Field(default=None, strict=True)

	@field_validator("name", "slug", "rules_engine_version", "is_active", mode="before")
	@classmethod
	def reject_explicit_null(cls, value):
		if value is None:
			raise ValueError("Поле не может иметь значение null")

		return value

class GameSystemsCatalogAccess(BaseModel):
	can_create: bool
	can_edit: bool
	can_toggle: bool
	can_delete: bool
	list_url: str