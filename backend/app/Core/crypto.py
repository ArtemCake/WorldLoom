# backend/app/core/crypto.py

"""Шифрование значений и поисковый HMAC адреса электронной почты.

Сохраняет алгоритмы старого backend/app/Core/crypto.py.

Импорт модуля не загружает настройки и не создаёт Fernet.
"""

from __future__ import annotations
import hashlib
import hmac
from functools import lru_cache
from cryptography.fernet import Fernet


class CryptoService:
	"""Криптографические операции с явно переданными ключами.

	Не генерирует и не меняет ключи.
	Не журналирует исходные значения, ключи или шифротекст.
	"""

	def __init__(self, *, encryption_key: str, email_hash_key: str) -> None:
		if not email_hash_key:
			raise ValueError(
				"EMAIL_HASH_KEY не должен быть пустым."
			)

		try:
			self._fernet = Fernet(
				encryption_key.encode("utf-8")
			)
		except ValueError:
			raise ValueError(
				"ENCRYPTION_KEY должен быть корректным ключом Fernet."
			) from None

		self._email_hash_key = email_hash_key.encode("utf-8")

	def encrypt_value(self, value: str) -> str:
		"""Зашифровать строку, сохранив формат старой реализации."""
		return self._fernet.encrypt(
			value.encode("utf-8")
		).decode("utf-8")

	def decrypt_value(self, token: str) -> str:
		"""Расшифровать строку.

		InvalidToken не перехватывается: неверный ключ,
		повреждённый или поддельный токен не превращаются
		в пустое значение.
		"""
		return self._fernet.decrypt(
			token.encode("utf-8")
		).decode("utf-8")

	def hash_email(self, email: str) -> str:
		"""Вычислить поисковый HMAC по прежним правилам."""
		normalized = email.strip().lower()

		return hmac.new(
			self._email_hash_key,
			normalized.encode("utf-8"),
			hashlib.sha256,
		).hexdigest()

@lru_cache(maxsize=1)
def get_crypto_service() -> CryptoService:
	"""Создать сервис при первом обращении, затем переиспользовать."""
	from backend.app.core.settings import get_settings

	settings = get_settings()

	return CryptoService(
		encryption_key=settings.ENCRYPTION_KEY,
		email_hash_key=settings.EMAIL_HASH_KEY,
	)

def encrypt_value(value: str) -> str:
	"""Совместимый интерфейс для переносимых потребителей."""
	return get_crypto_service().encrypt_value(value)

def decrypt_value(token: str) -> str:
	"""Совместимый интерфейс для переносимых потребителей."""
	return get_crypto_service().decrypt_value(token)

def hash_email(email: str) -> str:
	"""Совместимый интерфейс для переносимых потребителей."""
	return get_crypto_service().hash_email(email)