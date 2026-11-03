# backend/app/modules/users/schemas/schemas.py

"""Данные профиля и настройки оформления."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

class ProfileSettingsDTO(BaseModel):
	theme: Literal["dark-fantasy", "light-fantasy", "fantasy", "custom"] = Field(default="dark-fantasy", description="Выбранная тема оформления")
	theme_color: str | None = Field(default="#a855f7", description="Основной цвет темы")
	background_url: str | None = Field(default=None, description="Ссылка на фоновое изображение")

class UpdateThemeDTO(BaseModel):
	theme: Literal["dark-fantasy", "light-fantasy", "fantasy", "custom"]
	theme_color: str | None = None

class ProfileResponseDTO(BaseModel):
	id: UUID
	nickname: str
	email: EmailStr
	avatar_url: str | None = None
	is_email_verified: bool
	profile_settings: ProfileSettingsDTO