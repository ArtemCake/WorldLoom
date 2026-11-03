# backend/app/modules/auth/schemas.py

"""Входные данные регистрации и общее правило сложности пароля."""

import re
from pydantic import BaseModel, EmailStr, Field, field_validator


def validate_password_complexity(password: str) -> str | None:
	"""Вернуть сообщение об ошибке или None, если правило выполнено."""
	if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
		return "Пароль должен содержать буквы и цифры"
	return None

class RegisterRequest(BaseModel):
	"""Данные регистрации с сохранением прежних правил проверки."""

	nickname: str = Field(..., min_length=3, max_length=32, pattern=r"^[\w\-]+$", description="Никнейм (буквы, цифры, дефис, подчеркивание)")
	email: EmailStr = Field(..., description="Email пользователя")
	password: str = Field(..., min_length=8, max_length=128, description="Пароль")
	accepted_terms: bool = Field(..., description="Согласие с пользовательским соглашением и политикой конфиденциальности")

	@field_validator("password")
	@classmethod
	def check_password_complexity(cls, value: str) -> str:
		error = validate_password_complexity(value)
		if error:
			raise ValueError(error)
		return value

	@field_validator("accepted_terms")
	@classmethod
	def check_terms_accepted(cls, value: bool) -> bool:
		if not value:
			raise ValueError("Нужно подтвердить согласие с пользовательским соглашением и политикой конфиденциальности")
		return value