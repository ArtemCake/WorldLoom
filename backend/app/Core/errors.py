# backend/app/core/errors.py

"""Общие прикладные исключения.

Модуль не зависит от FastAPI, SQLAlchemy, настроек или журналирования.

Сообщения предназначены для описания ожидаемых отказов.
В них нельзя включать пароли, токены, SQL и другие внутренние данные.
"""
from typing import ClassVar


class AppError(Exception):
	"""Базовый класс ожидаемых прикладных ошибок.

	code — стабильное обозначение категории ошибки.
	message — понятное описание конкретного отказа.

	Преобразование в HTTP-ответ выполняется отдельно, в веб-слое.
	"""

	code: ClassVar[str] = "application_error"
	default_message: ClassVar[str] = "Не удалось выполнить операцию."

	def __init__(self, message: str | None = None) -> None:
		self.message = (
			self.default_message
			if message is None
			else message
		)

		super().__init__(self.message)

class AuthenticationRequiredError(AppError):
	"""Для операции требуется авторизованный пользователь."""

	code: ClassVar[str] = "authentication_required"
	default_message: ClassVar[str] = (
		"Требуется авторизованный пользователь."
	)

class NotFoundError(AppError):
	"""Ресурс не найден либо его существование не раскрывается."""

	code: ClassVar[str] = "not_found"
	default_message: ClassVar[str] = "Ресурс не найден."

class ConflictError(AppError):
	"""Операция конфликтует с текущим состоянием данных."""

	code: ClassVar[str] = "conflict"
	default_message: ClassVar[str] = (
		"Операция конфликтует с текущим состоянием данных."
	)