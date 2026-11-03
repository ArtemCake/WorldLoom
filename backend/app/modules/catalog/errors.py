# backend/app/modules/catalog/errors.py

"""Ожидаемые ошибки работы с каталогом."""

class CatalogError(Exception):
	"""Базовая ошибка каталога."""

class CatalogNotFound(CatalogError):
	"""Запрошенная запись не найдена."""

class CatalogConflict(CatalogError):
	"""Изменение конфликтует с существующими данными."""