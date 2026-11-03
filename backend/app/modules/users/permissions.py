# backend/app/modules/users/permissions.py

"""Правила административного доступа без HTTP и базы данных."""

from __future__ import annotations
from collections.abc import Collection
from backend.app.modules.users.enums import (AdminPermission, SystemRole)


def is_administrator(roles: Collection[SystemRole] | None) -> bool:
	"""Проверить наличие административной роли."""
	return SystemRole.ADMIN in (roles or ())

def has_admin_permission(roles: Collection[SystemRole] | None, permissions: Collection[AdminPermission] | None, permission: AdminPermission) -> bool:
	"""Требовать и роль администратора, и право раздела."""
	return (
			is_administrator(roles)
			and permission in (permissions or ())
	)

def get_self_editable_roles(roles: Collection[SystemRole] | None) -> list[SystemRole]:
	"""Вернуть роли, которыми пользователь может управлять в собственном профиле."""
	if is_administrator(roles):
		return list(SystemRole)
	return [SystemRole.PLAYER, SystemRole.MASTER]