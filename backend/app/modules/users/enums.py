# backend/app/modules/users/enums.py

"""Роли пользователей и административные разрешения.

Не зависит от SQLAlchemy, FastAPI, настроек и инфраструктуры.
Значения сохранены из старого Enums/enums_BD.py.
"""

from enum import StrEnum, unique


@unique
class SystemRole(StrEnum):
	"""Системные роли пользователя."""

	PLAYER = "player"
	MASTER = "master"
	EDITOR = "editor"
	ADMIN = "admin"

@unique
class AdminPermission(StrEnum):
	"""Разрешения на отдельные разделы администрирования.

	Наличие роли ADMIN и проверка конкретного разрешения —
	разные условия. Их применение относится к проверкам доступа,
	а не к самому перечислению.
	"""

	USERS = "users"
	CONTENT = "content"
	REPORTS = "reports"
	AUDIT = "audit"
	SYSTEM = "system"
