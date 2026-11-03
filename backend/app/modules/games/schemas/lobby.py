# backend/app/modules/games/schemas/lobby.py

"""Входные данные и представления игрового лобби."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


GameStatus = Literal["draft", "active", "archived"]
PrivacyLevel = Literal["public", "friends_only", "invite_only", "private"]
PartyRole = Literal["player", "assistant_dm", "banned"]


class GameCreate(BaseModel):
	system_id: UUID
	title: str = Field(min_length=1, max_length=255)
	description: str | None = None
	privacy_level: PrivacyLevel = "invite_only"
	voice_chat_config: dict | None = None
	is_homebrew_allowed: bool = False

	@field_validator("title", mode="before")
	@classmethod
	def normalize_title(cls, value: object) -> object:
		return value.strip() if isinstance(value, str) else value

class GameUpdate(BaseModel):
	title: str | None = Field(default=None, min_length=1, max_length=255)
	description: str | None = None
	status: GameStatus | None = None
	privacy_level: PrivacyLevel | None = None
	voice_chat_config: dict | None = None
	is_homebrew_allowed: bool | None = None

	@field_validator("title", mode="before")
	@classmethod
	def normalize_title(cls, value: object) -> object:
		return value.strip() if isinstance(value, str) else value

	@model_validator(mode="after")
	def reject_required_nulls(self) -> GameUpdate:
		for name in ("title", "status", "privacy_level", "is_homebrew_allowed"):
			if name in self.model_fields_set and getattr(self, name) is None:
				raise ValueError(f"Поле {name} не может быть null")

		return self

class GameRead(BaseModel):
	model_config = ConfigDict(from_attributes=True)

	id: UUID
	master_id: UUID | None
	system_id: UUID
	title: str
	description: str | None
	status: GameStatus
	privacy_level: PrivacyLevel
	voice_chat_config: dict | None
	is_homebrew_allowed: bool

class PartyRead(BaseModel):
	model_config = ConfigDict(from_attributes=True)

	game_id: UUID
	user_id: UUID
	role_in_game: PartyRole
	is_active: bool
	notification_settings: dict | None

class PartyRoleUpdate(BaseModel):
	role_in_game: PartyRole

class InviteCreate(BaseModel):
	expires_at: AwareDatetime | None = None
	uses_limit: int | None = Field(default=None, ge=1)
	message: str | None = None

class InviteRead(BaseModel):
	model_config = ConfigDict(from_attributes=True)

	token: str
	game_id: UUID
	creator_id: UUID | None
	claimed_by: UUID | None
	expires_at: datetime
	uses_limit: int
	uses_current: int
	message: str | None

class InviteClaim(BaseModel):
	token: str = Field(min_length=1, max_length=64)

class SessionCreate(BaseModel):
	title: str | None = Field(default=None, max_length=255)

class SessionUpdate(BaseModel):
	title: str | None = Field(default=None, max_length=255)
	summary_log: str | None = None

class SessionRead(BaseModel):
	model_config = ConfigDict(from_attributes=True)

	id: UUID
	game_id: UUID
	title: str | None
	summary_log: str | None
	start_time: datetime
	end_time: datetime | None
	is_active: bool
