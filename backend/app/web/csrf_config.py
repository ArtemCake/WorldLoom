# backend/app/web/csrf_config.py

"""Явная настройка CSRF при создании приложения."""

from __future__ import annotations
from threading import Lock
from typing import Literal
from fastapi_csrf_protect import CsrfProtect
from pydantic import BaseModel, Field
from backend.app.core.settings import WebAppSettings

class CsrfConfiguration(BaseModel):
	secret_key: str = Field(repr=False)
	cookie_samesite: Literal["lax"] = "lax"
	cookie_secure: bool
	header_name: str = "X-CSRF-Token"
	token_location: Literal["header"] = "header"

_configuration: CsrfConfiguration | None = None
_configuration_lock = Lock()

def configure_csrf(settings: WebAppSettings) -> None:
	"""Настроить библиотеку один раз для одной конфигурации процесса."""
	global _configuration

	configuration = CsrfConfiguration(
		secret_key=settings.SECRET_KEY,
		cookie_secure=bool(settings.SECURE_COOKIES),
	)

	with _configuration_lock:
		if _configuration is not None:
			if _configuration != configuration:
				raise RuntimeError("В одном процессе нельзя использовать разные настройки CSRF")

			return

		@CsrfProtect.load_config
		def load_configuration() -> CsrfConfiguration:
			return configuration

		_configuration = configuration
