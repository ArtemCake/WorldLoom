# backend/app/modules/users/api.py

"""Данные профиля, роли, оформление, пароль и управление MFA."""

from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.settings import WebAppSettings
from backend.app.infrastructure.database.session import get_async_session
from backend.app.modules.auth.cookies import clear_auth_cookies
from backend.app.modules.auth.dependencies import get_current_user
from backend.app.modules.auth.errors import InvalidCredentials
from backend.app.modules.auth.http import get_auth_notifications, get_auth_settings
from backend.app.modules.auth.services.email_verification import resend_verification
from backend.app.modules.auth.services.mfa import confirm_totp_setup, disable_mfa, start_totp_setup
from backend.app.modules.auth.services.notifications import AuthNotifications
from backend.app.modules.auth.services.rate_limit import check_ip_rate_limit
from backend.app.modules.users.enums import SystemRole
from backend.app.modules.users.http import ProfileRoute
from backend.app.modules.users.models.user import User
from backend.app.modules.users.schemas import ProfileResponseDTO, ProfileSettingsDTO, UpdateThemeDTO
from backend.app.web.csrf import enforce_csrf
import asyncio
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import EmailStr
from starlette.responses import FileResponse, JSONResponse, Response
from backend.app.modules.users.services.avatars import get_avatar_path, normalize_avatar_url, prepare_avatar
from backend.app.modules.users.services.profile import change_password, update_own_roles, update_theme, update_user_profile



router = APIRouter(prefix="/profile", tags=["profile"], route_class=ProfileRoute)
mutations = APIRouter(route_class=ProfileRoute, dependencies=[Depends(enforce_csrf)])

ProfileSession = Annotated[AsyncSession, Depends(get_async_session)]
ProfileSettings = Annotated[WebAppSettings, Depends(get_auth_settings)]
ProfileNotices = Annotated[AuthNotifications, Depends(get_auth_notifications)]
CurrentUser = Annotated[User, Depends(get_current_user)]

async def _limit_sensitive_action(request: Request, settings: WebAppSettings, action: str) -> None:
	"""Использовать отдельный счётчик чувствительных операций профиля."""
	client_ip = request.client.host if request.client else "unknown"
	key = f"{client_ip}:profile:{action}"
	limited = await check_ip_rate_limit(key, settings.LOGIN_IP_RATE_LIMIT, settings.LOGIN_IP_RATE_WINDOW_MINUTES)

	if limited:
		raise HTTPException(status_code=429, detail="Слишком много попыток. Попробуйте позже.")

@router.get("/data", response_model=ProfileResponseDTO, operation_id="getCurrentUserProfile")
async def get_profile_data(user: CurrentUser) -> ProfileResponseDTO:
	return ProfileResponseDTO(
		id=user.id, nickname=user.nickname, email=user.email, avatar_url=normalize_avatar_url(user.avatar_url),
		is_email_verified=user.is_email_verified,
		profile_settings=ProfileSettingsDTO(**(user.profile_settings or {})),
	)

@mutations.patch("/roles", operation_id="updateUserRoles")
async def api_update_roles(session: ProfileSession, user: CurrentUser, roles: list[SystemRole] = Form([])) -> dict[str, object]:
	updated_roles = await update_own_roles(session, user, roles)
	return {"message": "Роли обновлены.", "roles": [role.value for role in updated_roles]}

@mutations.patch("/theme", operation_id="updateUserTheme")
async def api_update_theme(payload: UpdateThemeDTO, session: ProfileSession, user: CurrentUser) -> dict[str, str]:
	theme = await update_theme(session, user, payload)
	return {"message": "Тема сохранена.", "theme": theme}

@mutations.post("/change-password", operation_id="changeUserPassword")
async def api_change_password(request: Request, session: ProfileSession, user: CurrentUser, settings: ProfileSettings,
		current_password: str = Form(...), new_password: str = Form(...)) -> Response:
	await _limit_sensitive_action(request, settings, "change_password")
	await change_password(session, user, current_password, new_password)

	response = JSONResponse(
		content={
			"message": "Пароль успешно изменён!",
			"security_note": "Активная сессия завершена. Войдите снова с новым паролем.",
			"redirect_url": "/login",
		},
	)
	clear_auth_cookies(response, settings=settings)
	return response

@mutations.post("/resend-verification", operation_id="resendOwnVerificationEmail")
async def api_resend_verification(request: Request, session: ProfileSession, user: CurrentUser, settings: ProfileSettings, notices: ProfileNotices) -> dict[str, str]:
	await _limit_sensitive_action(request, settings, "resend_verification")
	sent = await resend_verification(session, user.id, settings=settings, notifications=notices)
	message = "Письмо с подтверждением отправлено повторно." if sent else "Почта уже подтверждена."
	return {"message": message}

@mutations.post("/mfa/setup")
async def mfa_setup(request: Request, session: ProfileSession, user: CurrentUser, settings: ProfileSettings) -> Response:
	await _limit_sensitive_action(request, settings, "mfa_setup")
	secret, uri = await start_totp_setup(session, user, settings=settings)
	return JSONResponse(content={"secret": secret, "otpauth_uri": uri})

@mutations.post("/mfa/confirm")
async def mfa_confirm(request: Request, session: ProfileSession, user: CurrentUser, settings: ProfileSettings, code: str = Form(...)) -> Response:
	await _limit_sensitive_action(request, settings, "mfa_confirm")
	backup_codes = await confirm_totp_setup(session, user, code, settings=settings)

	if backup_codes is None:
		return JSONResponse(status_code=400, content={"error": "Неверный код. Проверьте время на устройстве и попробуйте снова."})

	return JSONResponse(
		content={"message": "Двухфакторная аутентификация включена. Сохраните резервные коды.", "backup_codes": backup_codes},
	)

@mutations.post("/mfa/disable")
async def mfa_disable(request: Request, session: ProfileSession, user: CurrentUser, settings: ProfileSettings, password: str = Form(...)) -> Response:
	await _limit_sensitive_action(request, settings, "mfa_disable")

	try:
		await disable_mfa(session, user, password)
	except InvalidCredentials:
		return JSONResponse(status_code=403, content={"error": "Неверный пароль."})

	return JSONResponse(content={"message": "Двухфакторная аутентификация отключена."})

@router.get("/avatars/{catalog}/{filename}", response_class=FileResponse, name="user_avatar")
async def user_avatar(catalog: str, filename: str) -> Response:
	"""Выдать PNG из закрытого каталога аватаров по серверному адресу.

	Имя каталога содержит идентификатор владельца, а имя файла — два
	hex-отпечатка uuid4, поэтому доступ разрешён без отдельной проверки сессии.
	"""
	try:
		path = await asyncio.to_thread(get_avatar_path, catalog, filename)
	except (FileNotFoundError, ValueError):
		raise HTTPException(status_code=404, detail="Аватар не найден.") from None

	return FileResponse(path, media_type="image/png", headers={"X-Content-Type-Options": "nosniff"})

@mutations.put("/update", operation_id="updateUserProfile")
async def api_update_profile(
		request: Request, session: ProfileSession, user: CurrentUser, settings: ProfileSettings, notices: ProfileNotices,
		nickname: str = Form(...), email: EmailStr = Form(...), avatar: UploadFile | None = File(None)) -> Response:
	await _limit_sensitive_action(request, settings, "update_profile")
	avatar_content = await prepare_avatar(avatar, settings=settings)
	result = await update_user_profile(
		session, user, nickname, str(email), avatar_content, settings=settings, notifications=notices,
	)

	if not result.email_changed:
		message = "Профиль успешно обновлен."
	elif result.mail_sent:
		message = "Профиль обновлён. На новый адрес отправлено письмо для подтверждения."
	else:
		message = "Профиль обновлён, но письмо с подтверждением не отправлено. Запросите его повторно из настроек аккаунта."

	return JSONResponse(content={"message": message, "avatar_url": normalize_avatar_url(result.avatar_url), "mail_sent": result.mail_sent})

router.include_router(mutations)