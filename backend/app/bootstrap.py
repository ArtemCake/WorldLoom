# backend/app/bootstrap.py

"""Сборка зависимостей приложения без запуска инфраструктуры."""

from __future__ import annotations
from dataclasses import dataclass
from backend.app.core.crypto import CryptoService
from backend.app.core.settings import WebAppSettings
from backend.app.infrastructure.database.session import Database


@dataclass(frozen=True, slots=True, repr=False)
class AppResources:
	"""Общие зависимости одного экземпляра приложения.

	repr отключён, чтобы случайный вывод контейнера
	не раскрывал содержимое настроек.
	"""

	settings: WebAppSettings
	crypto: CryptoService
	database: Database

def build_resources(settings: WebAppSettings) -> AppResources:
	"""Собрать зависимости из явно переданных настроек.

	Не читает .env самостоятельно и не проверяет подключение к БД.

	Криптография проверяется до создания движка:
	ошибочные ключи не оставляют уже созданный движок.
	"""
	crypto = CryptoService(
		encryption_key=settings.ENCRYPTION_KEY,
		email_hash_key=settings.EMAIL_HASH_KEY,
	)

	database = Database(settings.DATABASE_URL)

	return AppResources(
		settings=settings,
		crypto=crypto,
		database=database,
	)