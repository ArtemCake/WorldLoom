# backend/app/modules/users/errors.py

"""Ожидаемые ошибки операций с профилем."""

from backend.app.core.errors import AppError

class ProfileError(AppError):
	code = "profile_error"
	default_message = "Не удалось изменить профиль."

class ProfileSessionExpired(ProfileError):
	code = "profile_session_expired"
	default_message = "Сессия завершена, войдите снова."

class CurrentPasswordInvalid(ProfileError):
	code = "current_password_invalid"
	default_message = "Текущий пароль неверен. Операция отменена."

class ProfileConflict(ProfileError):
	code = "profile_conflict"
	default_message = "Email или никнейм уже занят."

class InvalidAvatar(ProfileError):
	code = "invalid_avatar"
	default_message = "Не удалось прочитать изображение аватара."

class AvatarTooLarge(InvalidAvatar):
	code = "avatar_too_large"
	default_message = "Файл аватара превышает допустимый размер."

class LocalPasswordRequired(ProfileError):
	code = "local_password_required"
	default_message = "Для этого аккаунта не задан пароль (вход через соцсеть). Удаление по паролю недоступно."

class AccountDeletionConflict(ProfileConflict):
	code = "account_deletion_conflict"
	default_message = "Не удалось удалить аккаунт из-за ограничений связанных данных. Изменения отменены."