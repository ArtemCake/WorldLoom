# backend/app/commands/create_initial_admin.py

"""Явное создание первого администратора без запуска веб-приложения."""

import asyncio
import sys
from typing import Literal
from pydantic import EmailStr, TypeAdapter
from sqlalchemy import func, insert, select, text, update
from backend.app.core.crypto import CryptoService
from backend.app.core.settings import WebAppSettings, get_settings
from backend.app.infrastructure.database.model_registry import configure_models
from backend.app.infrastructure.database.session import Database
from backend.app.modules.auth.services.passwords import hash_password
from backend.app.modules.users.enums import AdminPermission, SystemRole
from backend.app.modules.users.models.user import User


_USERS = User.__table__
_ADMIN_LOCK_NAME = "worldloom:create-initial-admin"
AdminCreationResult = Literal["exists", "promoted", "created"]

async def create_initial_admin(settings: WebAppSettings | None = None) -> AdminCreationResult:
	"""Создать или повысить первый аккаунт одной транзакцией."""
	current_settings = settings if settings is not None else get_settings()
	configure_models()

	crypto = CryptoService(
		encryption_key=current_settings.ENCRYPTION_KEY,
		email_hash_key=current_settings.EMAIL_HASH_KEY,
	)
	database = Database(current_settings.DATABASE_URL)

	try:
		async with database.session() as session:
			async with session.begin():
				await session.connection(execution_options={"isolation_level": "READ COMMITTED"})
				await session.execute(
					text("SELECT pg_advisory_xact_lock(hashtextextended(:name, 0))"),
					{"name": _ADMIN_LOCK_NAME},
				)

				existing_admin = await session.scalar(
					select(_USERS.c.id).where(_USERS.c.roles.any(SystemRole.ADMIN)).limit(1)
				)

				if existing_admin is not None:
					return "exists"

				email = str(TypeAdapter(EmailStr).validate_python(current_settings.ADMIN_EMAIL))
				email_hash = crypto.hash_email(email)
				result = await session.execute(
					select(_USERS.c.id, _USERS.c.roles, _USERS.c.is_active, _USERS.c.deleted_at)
					.where(_USERS.c.email_hash == email_hash)
					.with_for_update()
				)
				existing_user = result.mappings().one_or_none()

				if existing_user is not None:
					if not existing_user["is_active"] or existing_user["deleted_at"] is not None:
						raise RuntimeError("Настроенный аккаунт администратора отключён или удалён.")

					roles = list(dict.fromkeys([*(existing_user["roles"] or []), SystemRole.ADMIN]))

					await session.execute(
						update(_USERS)
						.where(_USERS.c.id == existing_user["id"])
						.values(roles=roles, admin_permissions=list(AdminPermission), updated_at=func.now())
					)
					return "promoted"

				nickname = current_settings.ADMIN_NICKNAME

				if not nickname.strip() or len(nickname) > 50:
					raise ValueError("ADMIN_NICKNAME должен содержать от 1 до 50 символов и не состоять из пробелов.")

				if not current_settings.ADMIN_PASSWORD.strip():
					raise ValueError("ADMIN_PASSWORD не должен быть пустым или состоять из пробелов.")

				nickname_owner = await session.scalar(
					select(_USERS.c.id).where(_USERS.c.nickname == nickname).limit(1)
				)

				if nickname_owner is not None:
					raise RuntimeError("ADMIN_NICKNAME уже используется другим аккаунтом.")

				password_hash = await asyncio.to_thread(hash_password, current_settings.ADMIN_PASSWORD)

				await session.execute(
					insert(_USERS).values(
						email_encrypted=crypto.encrypt_value(email),
						email_hash=email_hash,
						nickname=nickname,
						password_hash=password_hash,
						roles=[SystemRole.ADMIN],
						admin_permissions=list(AdminPermission),
						is_email_verified=True,
						is_active=True,
					)
				)
				return "created"
	finally:
		await database.dispose()

def main() -> int:
	try:
		result = asyncio.run(create_initial_admin())
	except Exception as error:
		print(
			f"Операция создания администратора не завершена. Тип ошибки: {type(error).__name__}.",
			file=sys.stderr,
		)
		print(
			"Проверьте миграции, подключение к БД, ключи шифрования и параметры ADMIN_EMAIL, ADMIN_NICKNAME, ADMIN_PASSWORD.",
			file=sys.stderr,
		)
		return 1

	messages = {
		"exists": "Администратор уже существует. Изменения не выполнялись.",
		"promoted": "Существующему аккаунту назначены роль администратора и все административные разрешения.",
		"created": "Первый администратор создан. Смените пароль после первого входа.",
	}
	print(messages[result])

	if result == "promoted":
		print("Пароль и состояние подтверждения почты существующего аккаунта сохранены.")

	return 0

if __name__ == "__main__":
	raise SystemExit(main())