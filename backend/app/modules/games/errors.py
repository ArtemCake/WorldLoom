# backend/app/modules/games/errors.py

"""Предметные ошибки лобби и удаления игр без зависимости от HTTP."""

from __future__ import annotations


class GameOperationError(Exception):
	"""Базовая ожидаемая ошибка операции лобби."""

class GameNotFound(GameOperationError):
	"""Запрошенная игра не найдена."""

class GameAccessDenied(GameOperationError):
	"""У пользователя нет доступа к операции."""

class GameSessionNotFound(GameOperationError):
	"""Игровая встреча не найдена."""

class GameStateConflict(GameOperationError):
	"""Текущее состояние не допускает операцию."""

class InvalidGameInput(GameOperationError):
	"""Переданы недопустимые параметры."""

class GameSystemNotFound(GameOperationError):
	"""Игровая система не найдена."""

class PartyMemberNotFound(GameOperationError):
	"""Участник игры не найден."""

class InviteNotFound(GameOperationError):
	"""Приглашение не найдено."""

class InviteExpired(GameOperationError):
	"""Приглашение истекло или исчерпано."""

class GameCommitOutcomeUnknown(GameOperationError):
	"""Результат фиксации операции не подтверждён."""

class GameDeletionError(Exception):
	"""Базовая ошибка удаления игры и подготовки очистки."""

class InvalidGameDeletion(GameDeletionError):
	"""Некорректные аргументы удаления."""

class GameDeletionForbidden(GameDeletionError):
	"""Удаление или очистка недоступны переданному пользователю."""

class GameDeletionConflict(GameDeletionError):
	"""Состояние не позволяет безопасно продолжить удаление."""

class GameCleanupJobNotFound(GameDeletionError):
	"""Сохранённое задание очистки не найдено."""