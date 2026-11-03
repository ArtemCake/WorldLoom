# backend/app/modules/auth/services/passwords.py

"""Хеширование паролей с параметрами старой реализации."""

from passlib.context import CryptContext


pwd_context = CryptContext(
	schemes=["argon2"], deprecated="auto", argon2__type="ID", argon2__memory_cost=19456, argon2__time_cost=3, argon2__parallelism=4, argon2__salt_len=16,
)

def hash_password(password: str) -> str:
	"""Создать Argon2id-хеш без изменения исходного пароля."""
	return pwd_context.hash(password)

def verify_password(password: str, password_hash: str) -> bool:
	"""Проверить пароль; некорректный хеш не разрешает вход."""
	try:
		return pwd_context.verify(password, password_hash)
	except (ValueError, TypeError):
		return False