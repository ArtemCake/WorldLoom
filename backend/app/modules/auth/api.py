# backend/app/modules/auth/api.py

"""HTTP-маршруты регистрации, входа и восстановления доступа."""

from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse, RedirectResponse, Response
from backend.app.core.logging import get_logger
from backend.app.core.settings import WebAppSettings
from backend.app.infrastructure.database.session import get_async_session
from backend.app.modules.auth.cookies import clear_auth_cookies, set_auth_cookies
from backend.app.modules.auth.dependencies import get_current_user
from backend.app.modules.auth.errors import AccountNotFound, InvalidSession
from backend.app.modules.auth.http import AuthErrorRoute, get_auth_notifications, get_auth_settings
from backend.app.modules.auth.schemas import RegisterRequest
from backend.app.modules.auth.services.authentication import login_with_password, logout_session, refresh_login_session
from backend.app.modules.auth.services.email_verification import confirm_email, resend_verification
from backend.app.modules.auth.services.mfa import login_with_mfa
from backend.app.modules.auth.services.notifications import AuthNotifications
from backend.app.modules.auth.services.password_reset import PASSWORD_RESET_REQUEST_MESSAGE, request_password_reset, reset_password
from backend.app.modules.auth.services.rate_limit import check_ip_rate_limit
from backend.app.modules.auth.services.registration import register_user
from backend.app.modules.users.models.user import User
from backend.app.web.csrf import enforce_csrf
from backend.app.modules.users.errors import CurrentPasswordInvalid, ProfileConflict, ProfileError, ProfileSessionExpired
from backend.app.modules.users.services.account_deletion import delete_current_account


log = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"], route_class=AuthErrorRoute)
mutations = APIRouter(route_class=AuthErrorRoute, dependencies=[Depends(enforce_csrf)])

AuthSession = Annotated[AsyncSession, Depends(get_async_session)]
AuthSettings = Annotated[WebAppSettings, Depends(get_auth_settings)]
AuthNotices = Annotated[AuthNotifications, Depends(get_auth_notifications)]
CurrentUser = Annotated[User, Depends(get_current_user)]

async def _check_rate_limit(request: Request, settings: WebAppSettings, scope: str = "") -> JSONResponse | None:
	"""Разделять счётчики разных сценариев, сохраняя старый ключ для входа."""
	client_ip = request.client.host if request.client else "unknown"
	rate_key = f"{client_ip}:{scope}" if scope else client_ip

	if await check_ip_rate_limit(rate_key, settings.LOGIN_IP_RATE_LIMIT, settings.LOGIN_IP_RATE_WINDOW_MINUTES):
		message = "Слишком много попыток входа. Попробуйте позже." if not scope else "Слишком много попыток. Попробуйте позже."
		return JSONResponse(status_code=429, content={"error": message})

	return None

def _login_response(tokens: dict[str, str], settings: WebAppSettings) -> JSONResponse:
	"""Сохранить JSON-контракт старого входа и установить cookie."""
	response = JSONResponse(
		content={"access_token": tokens["access_token"], "token_type": "bearer", "refresh_token": tokens["refresh_token"]},
	)
	set_auth_cookies(response, tokens, settings=settings)
	return response

@mutations.post("/register", status_code=201, name="register_user_action")
async def register_user_action(request: Request, data: RegisterRequest, session: AuthSession, settings: AuthSettings, notices: AuthNotices) -> Response:
	result = await register_user(session, data, settings=settings, notifications=notices)
	resend_url = str(request.app.url_path_for("resend_verification_email", user_id=str(result.user_id)))
	message = "Регистрация успешна! Письмо отправлено." if result.mail_sent else "Регистрация успешна, но ошибка отправки письма."

	return JSONResponse(status_code=201, content={"message": message, "resend_url": resend_url})

@mutations.post("/login", name="login_for_access_token")
async def login_for_access_token(request: Request, session: AuthSession, settings: AuthSettings, email: str = Form(...), password: str = Form(...)) -> Response:
	limited = await _check_rate_limit(request, settings)
	if limited is not None:
		return limited

	try:
		result = await login_with_password(session, email, password, settings=settings)
	except AccountNotFound:
		return JSONResponse(status_code=401, content={"error": "Аккаунт не найден.", "action": "account_not_found"})

	if result.mfa_required:
		return JSONResponse(
			content={"mfa_required": True, "mfa_token": result.mfa_token, "message": "Введите код двухфакторной аутентификации."},
		)

	if result.tokens is None:
		raise RuntimeError("Вход завершён без пары токенов")

	return _login_response(result.tokens, settings)

@mutations.post("/login/verify-mfa", name="login_verify_mfa")
async def login_verify_mfa(request: Request, session: AuthSession, settings: AuthSettings, mfa_token: str = Form(...), code: str = Form(...)) -> Response:
	limited = await _check_rate_limit(request, settings, "mfa_verify")
	if limited is not None:
		return limited

	try:
		tokens = await login_with_mfa(session, mfa_token, code, settings=settings)
	except InvalidSession as exc:
		return JSONResponse(status_code=400, content={"error": exc.message})

	return _login_response(tokens, settings)

@router.get("/verify-email", name="verify_email")
async def verify_email(token: str, session: AuthSession, settings: AuthSettings) -> Response:
	result = await confirm_email(session, token, settings=settings)
	return RedirectResponse(url=f"/login?verify={result}", status_code=303)

@mutations.post("/resend-verification/{user_id}", name="resend_verification_email")
async def resend_verification_email(request: Request, user_id: UUID, session: AuthSession, settings: AuthSettings, notices: AuthNotices) -> Response:
	limited = await _check_rate_limit(request, settings, "resend_verification")
	if limited is not None:
		return limited

	sent = await resend_verification(session, user_id, settings=settings, notifications=notices)
	message = "Письмо с подтверждением отправлено повторно." if sent else "Почта уже подтверждена, письмо не отправлено."
	return JSONResponse(content={"message": message})

@mutations.post("/refresh", name="refresh_access_token")
async def refresh_access_token(request: Request, session: AuthSession, settings: AuthSettings) -> Response:
	refresh_token = request.cookies.get("refresh_token")
	if not refresh_token:
		return JSONResponse(status_code=401, content={"detail": "Refresh-токен отсутствует."})

	try:
		tokens = await refresh_login_session(session, refresh_token, settings=settings)
	except InvalidSession as exc:
		return JSONResponse(status_code=401, content={"detail": exc.message})

	response = JSONResponse(content={"message": "Токен обновлён."})
	set_auth_cookies(response, tokens, settings=settings)
	return response

@mutations.post("/logout", name="logout")
async def logout(current_user: CurrentUser, session: AuthSession, settings: AuthSettings) -> Response:
	# Сохранить sid проверенного запроса до повторного чтения пользователя с блокировкой.
	user_id = current_user.id
	session_token = current_user.active_session_token
	if not session_token:
		raise InvalidSession()

	await logout_session(session, user_id, session_token)

	response = JSONResponse(content={"message": "Выход выполнен успешно"})
	clear_auth_cookies(response, settings=settings)
	response.headers["HX-Redirect"] = "/login"
	return response

@mutations.post("/forgot-password", name="forgot_password")
async def forgot_password(request: Request, session: AuthSession, settings: AuthSettings, notices: AuthNotices, email: str = Form(...)) -> Response:
	limited = await _check_rate_limit(request, settings, "password_reset")
	if limited is not None:
		return limited

	try:
		await request_password_reset(session, email, settings=settings, notifications=notices)
	except Exception as exc:
		await session.rollback()
		log.error("Запрос восстановления не завершён. Тип ошибки: %s", type(exc).__name__)

	# Не раскрывать существование аккаунта и результат отправки письма.
	return JSONResponse(content={"message": PASSWORD_RESET_REQUEST_MESSAGE})

@mutations.post("/reset-password", name="reset_password_action")
async def reset_password_action(session: AuthSession, settings: AuthSettings, token: str = Form(...), new_password: str = Form(...)) -> Response:
	await reset_password(session, token, new_password, settings=settings)

	response = JSONResponse(
		content={"message": "Пароль успешно изменён. Теперь можно войти с новым паролем.", "redirect_url": "/login"},
	)
	clear_auth_cookies(response, settings=settings)
	return response

@mutations.post("/delete-account", name="delete_account")
async def delete_account(request: Request, session: AuthSession, current_user: CurrentUser, settings: AuthSettings,
		password: str = Form(...), permanent: bool = Form(False)) -> Response:
	limited = await _check_rate_limit(request, settings, "delete_account")
	if limited is not None:
		return limited

	try:
		await delete_current_account(session, current_user, password, permanent=permanent)
	except ProfileError as exc:
		headers: dict[str, str] = {}

		if isinstance(exc, (CurrentPasswordInvalid, ProfileSessionExpired)):
			status_code = 401
			headers["WWW-Authenticate"] = "Bearer"
		elif isinstance(exc, ProfileConflict):
			status_code = 409
		else:
			status_code = 400

		return JSONResponse(status_code=status_code, content={"detail": exc.message}, headers=headers)

	response = JSONResponse(content={"message": "Аккаунт удалён."})
	clear_auth_cookies(response, settings=settings)
	response.headers["HX-Redirect"] = "/login"
	return response

router.include_router(mutations)