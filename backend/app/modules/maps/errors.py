# backend/app/modules/maps/errors.py

"""Предметные ошибки хранения и подготовки изображений карт."""


class MapStorageError(Exception):
	"""Базовая ошибка назначения адреса изображения карты."""

class InvalidMapStorage(MapStorageError):
	"""Некорректные аргументы назначения адреса."""

class MapStorageNotFound(MapStorageError):
	"""Игра или её владелец не найдены."""

class MapStorageForbidden(MapStorageError):
	"""Пользователь не может назначать адреса карт этой игры."""

class MapStorageConflict(MapStorageError):
	"""Сохранённое состояние не позволяет назначить адрес."""

class MapImageError(Exception):
	"""Базовая ошибка подготовки изображения карты."""

class InvalidMapImage(MapImageError):
	"""Файл не является допустимым изображением карты."""

class MapImageTooLarge(MapImageError):
	"""Исходный файл превышает допустимый объём загрузки."""

class InvalidMapImageKey(MapImageError):
	"""Некорректный адрес изображения или недопустимый путь хранилища."""

class MapImageNotFound(MapImageError):
	"""Файл фонового изображения не найден."""

class MapImageStorageFailure(MapImageError):
	"""Файловая операция с изображением завершилась ошибкой."""

class MapOperationError(Exception):
	"""Базовая ошибка операции управления картами."""

class InvalidMapOperation(MapOperationError):
	"""Некорректные аргументы операции управления картами."""

class MapEntityNotFound(MapOperationError):
	"""Карта или связанная с операцией игра не найдена."""

class MapAccessDenied(MapOperationError):
	"""Недостаточно прав для операции управления картой."""

class MapStateConflict(MapOperationError):
	"""Состояние карты изменилось и требует повторного чтения."""

class MapMoveBlocked(MapStateConflict):
	"""Перемещение карты запрещено из-за связанных игровых объектов."""

class MapCommitOutcomeUnknown(MapOperationError):
	"""Фиксация завершилась ошибкой; результат требует проверки по БД."""