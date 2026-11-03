# backend/app/modules/admin/pages.py

"""HTML-страницы административной панели."""

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi_csrf_protect import CsrfProtect
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import HTMLResponse, RedirectResponse
from backend.app.infrastructure.database.session import get_async_session
from backend.app.modules.admin import service
from backend.app.modules.admin.dependencies import get_admin_user, require_permission
from backend.app.modules.admin.schemas import ReportStatus
from backend.app.modules.users.enums import AdminPermission, SystemRole
from backend.app.modules.users.models.user import User
from backend.app.web.rendering import render_page


SessionDependency = Annotated[AsyncSession, Depends(get_async_session)]
CsrfDependency = Annotated[CsrfProtect, Depends()]
AdminUser = Annotated[User, Depends(get_admin_user)]
UserManager = Annotated[User, Depends(require_permission(AdminPermission.USERS))]
ReportManager = Annotated[User, Depends(require_permission(AdminPermission.REPORTS))]
AuditReader = Annotated[User, Depends(require_permission(AdminPermission.AUDIT))]

ROLE_LABELS = {
	SystemRole.PLAYER: "Игрок",
	SystemRole.MASTER: "Мастер (ведущий)",
	SystemRole.EDITOR: "Редактор контента",
	SystemRole.ADMIN: "Администратор",
}

PERMISSION_LABELS = {
	AdminPermission.USERS: "Пользователи",
	AdminPermission.CONTENT: "Контент",
	AdminPermission.REPORTS: "Жалобы",
	AdminPermission.AUDIT: "Аудит-лог",
	AdminPermission.SYSTEM: "Система",
}

router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/", response_class=HTMLResponse, name="admin_dashboard_get")
async def dashboard(request: Request, user: AdminUser, csrf_protect: CsrfDependency) -> HTMLResponse:
	context = {"user": user, "permission_labels": PERMISSION_LABELS}
	return render_page(request, "admin/dashboard.html", context, csrf_protect)

@router.get("/users", response_class=HTMLResponse, name="admin_users_get")
async def users_page(request: Request, session: SessionDependency, user: UserManager, csrf_protect: CsrfDependency,
                     search: str | None = None, page: int = Query(default=1, ge=1)) -> HTMLResponse:
	users, total = await service.list_users(session, search=search, page=page)
	context = {
		"user": user,
		"users": users,
		"total": total,
		"page": page,
		"page_size": service.PAGE_SIZE,
		"search": search or "",
		"role_labels": ROLE_LABELS,
		"all_roles": list(SystemRole),
		"all_permissions": list(AdminPermission),
		"permission_labels": PERMISSION_LABELS,
	}

	return render_page(request, "admin/users.html", context, csrf_protect)

@router.get("/reports", response_class=HTMLResponse, name="admin_reports_get")
async def reports_page(request: Request, session: SessionDependency, user: ReportManager, csrf_protect: CsrfDependency,
                       status_filter: str | None = None, page: int = Query(default=1, ge=1)) -> HTMLResponse:
	try:
		selected_status = ReportStatus(status_filter) if status_filter else None
	except ValueError:
		raise HTTPException(status_code=422, detail="Неизвестный статус жалобы.", headers={"Cache-Control": "no-store"}) from None

	reports, total = await service.list_reports(session, status_filter=selected_status, page=page)
	context = {
		"user": user,
		"reports": reports,
		"total": total,
		"page": page,
		"page_size": service.PAGE_SIZE,
		"status_filter": selected_status.value if selected_status is not None else "",
	}

	return render_page(request, "admin/reports.html", context, csrf_protect)

@router.get("/audit", response_class=HTMLResponse, name="admin_audit_get")
async def audit_page(request: Request, session: SessionDependency, user: AuditReader, csrf_protect: CsrfDependency,
                     page: int = Query(default=1, ge=1)) -> HTMLResponse:
	logs, total = await service.list_audit_logs(session, page=page)
	context = {"user": user, "logs": logs, "total": total, "page": page, "page_size": service.PAGE_SIZE}
	return render_page(request, "admin/audit.html", context, csrf_protect)

@router.get("/game-systems", response_class=RedirectResponse, name="admin_game_systems_get", operation_id="adminGameSystemsPage")
async def game_systems_redirect() -> RedirectResponse:
	return RedirectResponse(url="/game-systems/catalog", status_code=303, headers={"Cache-Control": "no-store"})