# backend/app/modules/users/pages.py

"""HTML-страница профиля."""

from fastapi import APIRouter, Depends, Request
from fastapi_csrf_protect import CsrfProtect
from starlette.responses import HTMLResponse

from backend.app.modules.auth.dependencies import get_current_user
from backend.app.modules.users.enums import SystemRole
from backend.app.modules.users.http import ProfileRoute
from backend.app.modules.users.models.user import User
from backend.app.modules.users.permissions import get_self_editable_roles
from backend.app.web.rendering import render_page


router = APIRouter(prefix="/profile", tags=["profile"], route_class=ProfileRoute)

ROLE_LABELS: dict[SystemRole, str] = {
	SystemRole.PLAYER: "Игрок",
	SystemRole.MASTER: "Мастер (ведущий)",
	SystemRole.EDITOR: "Редактор контента",
	SystemRole.ADMIN: "Администратор",
}

@router.get("/", response_class=HTMLResponse, name="profile_page_get")
async def get_profile_page(request: Request, user: User = Depends(get_current_user), csrf_protect: CsrfProtect = Depends()) -> HTMLResponse:
	editable_roles = get_self_editable_roles(user.roles)
	locked_roles = [role for role in (user.roles or []) if role not in editable_roles]
	context = {
		"user": user,
		"editable_roles": editable_roles,
		"locked_roles": locked_roles,
		"role_labels": ROLE_LABELS,
		"verification_required_notice": request.query_params.get("verify") == "required",
	}
	return render_page(request, "users/profile.html", context, csrf_protect)