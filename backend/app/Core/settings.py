# backend/app/core/settings.py

"""Загрузка и проверка конфигурации приложения."""

from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

from backend.app.core.paths import ENV_FILE, PROJECT_ROOT


TIMER_DEFAULT_INTERVAL_MIN = 5

class WebAppSettings(BaseSettings):
	"""Настройки из переменных окружения и data/.env."""

	model_config = SettingsConfigDict(
		env_file=ENV_FILE,
		env_file_encoding="utf-8",
		case_sensitive=False,
		extra="ignore",
		populate_by_name=True,
		hide_input_in_errors=True,
	)

	# Основной почтовый сервер.
	SMTP_HOST: str
	SMTP_PORT: int = Field(ge=1, le=65535)
	SMTP_USE_TLS: bool
	SMTP_USE_SSL: bool
	SMTP_USER: str
	SMTP_PASSWORD: str = Field(repr=False)

	# Резервный почтовый сервер.
	SMTP_FALLBACK_HOST: str | None = None
	SMTP_FALLBACK_PORT: int | None = Field(
		default=None,
		ge=1,
		le=65535,
	)
	SMTP_FALLBACK_USE_TLS: bool = True
	SMTP_FALLBACK_USE_SSL: bool = False
	SMTP_FALLBACK_USER: str | None = None
	SMTP_FALLBACK_PASSWORD: str | None = Field(
		default=None,
		repr=False,
	)

	MAIL_SENDER_NAME: str
	MAIL_SENDER_EMAIL: str
	MAIL_SUPPORT_EMAIL: str
	MAIL_FALLBACK_SENDER_EMAIL: str | None = None

	MAIL_SENDER_NAME: str
	MAIL_SENDER_EMAIL: str
	MAIL_SUPPORT_EMAIL: str


# Приложение.
	API_V1_STR: str = "/api/v1"
	PROJECT_NAME: str = "WorldLoom"
	DESCRIPTION: str = "Сайт для игры в НРИ онлайн"
	VERSION: str = "1.0.0"

	ENVIRONMENT: Literal[
		"development",
		"production",
		"testing",
	] = "development"

	FRONTEND_URL: str

	# Аватары: ограничения входного изображения и размер сохранённой копии.
	AVATAR_MAX_BYTES: int = Field(default=5 * 1024 * 1024, gt=0)
	AVATAR_MAX_PIXELS: int = Field(default=16_000_000, gt=0)
	AVATAR_MAX_SIDE: int = Field(default=8192, gt=0)
	AVATAR_OUTPUT_SIDE: int = Field(default=512, gt=0, le=2048)

	# PostgreSQL.
	POSTGRES_USER: str
	POSTGRES_PASSWORD: str = Field(repr=False)
	POSTGRES_DB: str
	POSTGRES_HOST: str
	POSTGRES_PORT: int = Field(ge=1, le=65535)

	ASYNC_DB_DRIVER: str = "postgresql+asyncpg"

	# Ключи и авторизация.
	SECRET_KEY: str = Field(repr=False)
	ENCRYPTION_KEY: str = Field(repr=False)
	EMAIL_HASH_KEY: str = Field(repr=False)

	ALGORITHM: str = "HS256"
	ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
		default=30,
		gt=0,
	)

	# None означает: вычислить по ENVIRONMENT после загрузки.
	SECURE_COOKIES: bool | None = None

	# Параметры явной команды создания администратора.
	ADMIN_PASSWORD: str = Field(repr=False)
	ADMIN_EMAIL: str
	ADMIN_NICKNAME: str

	# Ограничения входа.
	LOGIN_MAX_FAILED_ATTEMPTS: int = Field(gt=0)
	LOGIN_LOCKOUT_MINUTES: int = Field(gt=0)
	LOGIN_IP_RATE_LIMIT: int = Field(gt=0)
	LOGIN_IP_RATE_WINDOW_MINUTES: int = Field(gt=0)

	TIMER_DEFAULT_INTERVAL_MIN: int = Field(
		default=TIMER_DEFAULT_INTERVAL_MIN,
		gt=0,
	)

	# Сохраняем прежнее имя переменной окружения.
	BACKEND_CORS_ORIGINS_RAW: str = Field(
		default="",
		alias="BACKEND_CORS_ORIGINS",
	)

	# Изображения карт.
	MAP_IMAGES_DIR: Path | None = Path("uploads")
	MAP_IMAGE_MAX_BYTES: int = Field(
		default=10 * 1024 * 1024,
		gt=0,
	)
	MAP_IMAGE_MAX_PIXELS: int = Field(
		default=16_000_000,
		gt=0,
	)
	MAP_IMAGE_MAX_SIDE: int = Field(
		default=8192,
		gt=0,
	)

	@model_validator(mode="after")
	def configure_secure_cookies(self) -> Self:
		"""Определить защиту cookie по загруженной конфигурации."""
		if self.SECURE_COOKIES is None:
			self.SECURE_COOKIES = self.ENVIRONMENT == "production"

		if (
				self.ENVIRONMENT == "production"
				and self.SECURE_COOKIES is False
		):
			raise ValueError(
				"В production требуется SECURE_COOKIES=true."
			)

		return self

	@property
	def BASE_DIR(self) -> str:
		"""Корень проекта; строковый контракт старой конфигурации."""
		return PROJECT_ROOT.as_posix()

	@property
	def DATABASE_URL(self) -> str:
		"""URL подключения с экранированием реквизитов.

		Возвращаемое значение содержит пароль.
		Его нельзя записывать в журналы.
		"""
		url = URL.create(
			drivername=self.ASYNC_DB_DRIVER,
			username=self.POSTGRES_USER,
			password=self.POSTGRES_PASSWORD,
			host=self.POSTGRES_HOST,
			port=self.POSTGRES_PORT,
			database=self.POSTGRES_DB,
		)
		return url.render_as_string(hide_password=False)

	@property
	def BACKEND_CORS_ORIGINS(self) -> list[str]:
		"""Список разрешённых источников из строки через запятую."""
		return [
			origin.strip()
			for origin in self.BACKEND_CORS_ORIGINS_RAW.split(",")
			if origin.strip()
		]

@lru_cache(maxsize=1)
def get_settings() -> WebAppSettings:
	"""Загрузить настройки один раз на процесс."""
	try:
		return WebAppSettings()
	except ValidationError as error:
		# Не включаем исходные значения и сообщения валидаторов:
		# они могут содержать чувствительные данные.
		details = "; ".join(
			(
					".".join(str(part) for part in item["loc"])
					or "конфигурация"
			)
			+ f" ({item['type']})"
			for item in error.errors(
				include_input=False,
				include_context=False,
				include_url=False,
			)
		)

		raise RuntimeError(
			f"Ошибка конфигурации: проверьте параметры: {details}"
		) from None
