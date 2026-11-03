# backend/app/modules/admin/dependencies.py

"""HTTP-зависимости доступа к административным разделам."""

from __future__ import annotations
from collections.abc import Awaitable, Callable
from fastapi import Depends, HTTPException, status
from backend.app.modules.auth.dependencies import (get_current_user)
from backend.app.modules.users.enums import AdminPermission
from backend.app.modules.users.models.user import User
from backend.app.modules.users.permissions import (has_admin_permission, is_administrator)


async def get_admin_user(user: User = Depends(get_current_user)) -> User:
	"""Потребовать административную роль."""
	if not is_administrator(user.roles):
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="Требуются права администратора",
		)

	return user

def require_permission(permission: AdminPermission) -> Callable[..., Awaitable[User]]:
	"""Создать зависимость проверки конкретного права раздела."""
	if not isinstance(permission, AdminPermission):
		raise TypeError(
			"Разрешение должно быть элементом AdminPermission"
		)

	async def dependency(user: User = Depends(get_admin_user)) -> User:
		if not has_admin_permission(
				user.roles,
				user.admin_permissions,
				permission,
		):
			raise HTTPException(
				status_code=status.HTTP_403_FORBIDDEN,
				detail="Нет права доступа к этому разделу",
			)

		return user

	return dependency

require_content_manager = require_permission(
	AdminPermission.CONTENT
)