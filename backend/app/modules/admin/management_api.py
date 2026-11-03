# backend/app/modules/admin/management_api.py

"""Административное управление пользователями и жалобами."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Form, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.infrastructure.database.session import get_async_session
from backend.app.modules.admin import service
from backend.app.modules.admin.dependencies import require_permission
from backend.app.modules.admin.errors import AdminInvalidOperation, AdminNotFound
from backend.app.modules.admin.schemas import ReportStatus
from backend.app.modules.users.enums import AdminPermission, SystemRole
from backend.app.modules.users.errors import ProfileConflict, ProfileError, ProfileSessionExpired
from backend.app.modules.users.models.user import User
from backend.app.modules.users.services.account_deletion import hard_delete_user, soft_delete_user
from backend.app.web.csrf import enforce_csrf


SessionDependency = Annotated[AsyncSession, Depends(get_async_session)]
UserManager = Annotated[User, Depends(require_permission(AdminPermission.USERS))]
ReportManager = Annotated[User, Depends(require_permission(AdminPermission.REPORTS))]

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(enforce_csrf)])

def _http_error(status_code: int, detail: str) -> HTTPException:
	return HTTPException(status_code=status_code, detail=detail, headers={"Cache-Control": "no-store"})

@asynccontextmanager
async def _operation(session: AsyncSession, *, commit: bool = True) -> AsyncIterator[None]:
	try:
		yield

		if commit:
			await session.commit()
	except AdminNotFound as exc:
		await session.rollback()
		raise _http_error(404, str(exc)) from None
	except AdminInvalidOperation as exc:
		await session.rollback()
		raise _http_error(400, str(exc)) from None
	except ProfileSessionExpired as exc:
		await session.rollback()
		raise HTTPException(
			status_code=401, detail=exc.message, headers={"Cache-Control": "no-store", "WWW-Authenticate": "Bearer"},
		) from None
	except ProfileConflict as exc:
		await session.rollback()
		raise _http_error(409, exc.message) from None
	except ProfileError as exc:
		await session.rollback()
		raise _http_error(400, exc.message) from None
	except IntegrityError:
		await session.rollback()
		raise _http_error(409, "Изменение невозможно из-за ограничений связанных данных.") from None
	except BaseException:
		await session.rollback()
		raise

@router.patch("/users/{user_id}/roles", operation_id="adminUpdateUserRoles")
async def update_user_roles(user_id: UUID, session: SessionDependency, actor: UserManager, roles: list[SystemRole] = Form([])) -> dict:
	async with _operation(session):
		target = await service.admin_set_roles(session, user_id, roles)
		result = {"message": "Роли обновлены.", "roles": [role.value for role in target.roles]}

	return result

@router.patch("/users/{user_id}/permissions", operation_id="adminUpdateUserPermissions")
async def update_user_permissions(user_id: UUID, session: SessionDependency, actor: UserManager,
                                  permissions: list[AdminPermission] = Form([])) -> dict:
	async with _operation(session):
		target = await service.admin_set_permissions(session, user_id, permissions)
		result = {"message": "Права обновлены.", "permissions": [permission.value for permission in target.admin_permissions]}

	return result

@router.post("/users/{user_id}/delete", operation_id="adminDeleteUser")
async def delete_user(user_id: UUID, session: SessionDependency, actor: UserManager, permanent: bool = Form(False)) -> dict:
	if user_id == actor.id:
		raise _http_error(400, "Свой аккаунт удаляйте через настройки профиля, а не через админ-панель.")

	# Эти два сервиса уже выполняют commit и очистку аватара после него.
	# Повторную фиксацию во внешнем адаптере не добавляем.
	async with _operation(session, commit=False):
		await service.get_target_user(session, user_id)

		if permanent:
			await hard_delete_user(session, user_id)
			result = {"message": "Пользователь удалён навсегда."}
		else:
			changed = await soft_delete_user(session, user_id)

			if not changed:
				raise AdminInvalidOperation("Пользователь уже деактивирован.")

			result = {"message": "Пользователь деактивирован."}

	return result

@router.patch("/reports/{report_id}", operation_id="adminUpdateReport")
async def update_report(report_id: UUID, session: SessionDependency, actor: ReportManager,
                        new_status: ReportStatus = Form(...), moderator_note: str | None = Form(None)) -> dict:
	async with _operation(session):
		report = await service.update_report(session, report_id, new_status, moderator_note)
		result = {"message": "Жалоба обновлена.", "status": report.status}

	return result