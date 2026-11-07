# backend/app/modules/game_systems/errors.py

"""Предметные ошибки игровых систем без зависимости от HTTP."""

class GameSystemError(Exception):
	"""Базовая ошибка операций с игровой системой."""

class GameSystemNotFound(GameSystemError):
	"""Система или запрошенная публикация недоступна."""

class GameSystemRulesConflict(GameSystemError):
	"""Состояние системы не соответствует ожидаемому."""

class GameSystemDeletionBlocked(GameSystemRulesConflict):
	"""Удаление блокируют связанные данные; содержат перечень связей."""

	def __init__(self, message: str, blockers: tuple[str, ...]) -> None:
		super().__init__(message)
		self.blockers = blockers

class InvalidGameSystemRules(GameSystemError):
	"""Переданный профиль правил недопустим."""

class GameSystemRulesStorageError(GameSystemError):
	"""Сохранённые правила не соответствуют поддерживаемому формату."""