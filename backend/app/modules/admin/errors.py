# backend/app/modules/admin/errors.py

"""Ожидаемые ошибки административных операций."""

class AdminError(Exception):
	"""Базовая ошибка с безопасным сообщением для клиента."""

class AdminNotFound(AdminError):
	"""Запрошенная запись не найдена."""

class AdminInvalidOperation(AdminError):
	"""Изменение не соответствует правилам операции."""