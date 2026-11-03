# backend/app/modules/characters/errors.py

"""Ошибки работы с персонажами и их числовым состоянием."""


class CharacterError(Exception):
	"""Базовая ошибка модуля персонажей."""

class CharacterNotFound(CharacterError):
	"""Объект отсутствует или недоступен пользователю."""

class CharacterAccessDenied(CharacterError):
	"""Пользователю недоступна операция в игре."""

class CharacterStateNotInitialized(CharacterError):
	"""Запись ещё не переведена на универсальное состояние."""

class CharacterStateConflict(CharacterError):
	"""Изменилась ревизия записи или закреплённая публикация."""

class CharacterStateStorageError(CharacterError):
	"""Сохранённое состояние или правила некорректны."""

class InvalidCharacterStateChange(CharacterError):
	"""Изменение не соответствует закреплённым правилам."""