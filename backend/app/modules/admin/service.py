# backend/app/modules/admin/service.py

"""Административные операции без HTTP и самостоятельной фиксации транзакций."""

from uuid import UUID
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import lazyload
from backend.app.core.crypto import hash_email
from backend.app.modules.admin.errors import AdminInvalidOperation, AdminNotFound
from backend.app.modules.admin.models.audit_log import AuditLog
from backend.app.modules.admin.models.content_report import ContentReport
from backend.app.modules.admin.schemas import ReportStatus
from backend.app.modules.users.enums import AdminPermission, SystemRole
from backend.app.modules.users.models.user import User
from backend.app.modules.users.services.users import get_user_by_id


PAGE_SIZE = 25

def _page_offset(page: int) -> int:
	if page < 1:
		raise AdminInvalidOperation("Номер страницы должен быть положительным.")

	return (page - 1) * PAGE_SIZE

async def list_users(session: AsyncSession, search: str | None = None, page: int = 1) -> tuple[list[User], int]:
	offset = _page_offset(page)
	query = select(User).options(lazyload("*"))
	count_query = select(func.count()).select_from(User)
	search_value = search.strip() if search else ""

	if search_value:
		condition = or_(User.nickname.ilike(f"%{search_value}%"), User.email_hash == hash_email(search_value))
		query = query.where(condition)
		count_query = count_query.where(condition)

	total = (await session.execute(count_query)).scalar_one()
	query = query.order_by(User.created_at.desc(), User.id.desc()).offset(offset).limit(PAGE_SIZE)
	users = (await session.execute(query)).scalars().all()

	return list(users), total

async def get_target_user(session: AsyncSession, user_id: UUID) -> User:
	target = await get_user_by_id(session, user_id, for_update=True)

	if target is None:
		raise AdminNotFound("Пользователь не найден.")

	return target

async def admin_set_roles(session: AsyncSession, user_id: UUID, roles: list[SystemRole]) -> User:
	if not roles:
		raise AdminInvalidOperation("У пользователя должна остаться хотя бы одна роль.")

	target = await get_target_user(session, user_id)
	target.roles = list(dict.fromkeys(roles))

	if SystemRole.ADMIN not in target.roles:
		target.admin_permissions = []

	await session.flush()
	return target

async def admin_set_permissions(session: AsyncSession, user_id: UUID, permissions: list[AdminPermission]) -> User:
	target = await get_target_user(session, user_id)

	if SystemRole.ADMIN not in (target.roles or []):
		raise AdminInvalidOperation("Права разделов назначаются только пользователям с ролью «Администратор».")

	target.admin_permissions = list(dict.fromkeys(permissions))
	await session.flush()
	return target

async def list_reports(session: AsyncSession, status_filter: ReportStatus | None = None, page: int = 1) -> tuple[list[ContentReport], int]:
	offset = _page_offset(page)
	query = select(ContentReport).options(lazyload("*"))
	count_query = select(func.count()).select_from(ContentReport)

	if status_filter is not None:
		condition = ContentReport.status == status_filter.value
		query = query.where(condition)
		count_query = count_query.where(condition)

	total = (await session.execute(count_query)).scalar_one()
	query = query.order_by(ContentReport.created_at.desc(), ContentReport.id.desc()).offset(offset).limit(PAGE_SIZE)
	reports = (await session.execute(query)).scalars().all()

	return list(reports), total

async def get_report_by_id(session: AsyncSession, report_id: UUID, *, for_update: bool = False) -> ContentReport | None:
	query = select(ContentReport).where(ContentReport.id == report_id).options(lazyload("*")).execution_options(populate_existing=True)

	if for_update:
		query = query.with_for_update()

	return (await session.execute(query)).scalar_one_or_none()

async def update_report(session: AsyncSession, report_id: UUID, new_status: ReportStatus, note: str | None = None) -> ContentReport:
	report = await get_report_by_id(session, report_id, for_update=True)

	if report is None:
		raise AdminNotFound("Жалоба не найдена.")

	report.status = new_status.value

	if note is not None:
		report.moderator_note = note

	await session.flush()
	return report

async def list_audit_logs(session: AsyncSession, page: int = 1) -> tuple[list[AuditLog], int]:
	offset = _page_offset(page)
	count_query = select(func.count()).select_from(AuditLog)
	total = (await session.execute(count_query)).scalar_one()
	query = select(AuditLog).options(lazyload("*")).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
	query = query.offset(offset).limit(PAGE_SIZE)
	logs = (await session.execute(query)).scalars().all()

	return list(logs), total