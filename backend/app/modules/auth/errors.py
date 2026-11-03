# backend/app/modules/auth/errors.py

"""Прикладные ошибки авторизации без привязки к HTTP."""

from backend.app.core.errors import AppError


class AuthError(AppError):
	"""Базовая ошибка операции авторизации."""

	code = "auth_error"
	default_message = "Не удалось выполнить авторизацию."

class AccountNotFound(AuthError):
	"""Аккаунт с указанным адресом не найден."""

	code = "account_not_found"
	default_message = "Аккаунт не найден."

class InvalidCredentials(AuthError):
	"""Пароль неверен либо вход в аккаунт недоступен."""

	code = "invalid_credentials"
	default_message = "Неверный пароль."

class AccountLocked(AuthError):
	"""Вход временно заблокирован из-за неудачных попыток."""

	code = "account_locked"
	default_message = "Аккаунт временно заблокирован из-за множества неверных попыток входа."

	def __init__(self, retry_after_seconds: int) -> None:
		self.retry_after_seconds = max(1, retry_after_seconds)
		super().__init__()

class InvalidSession(AuthError):
	"""Токен недействителен либо сессия уже завершена."""

	code = "invalid_session"
	default_message = "Сессия завершена, войдите снова."

class RegistrationConflict(AuthError):
	"""Email или никнейм уже занят."""

	code = "registration_conflict"
	default_message = "Пользователь с такими данными уже существует."

class MailDeliveryError(AuthError):
	"""Почтовый транспорт не подтвердил отправку."""

	code = "mail_delivery_error"
	default_message = "Не удалось отправить письмо. Попробуйте позже."
