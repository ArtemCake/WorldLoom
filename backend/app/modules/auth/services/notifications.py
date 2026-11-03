# backend/app/modules/auth/services/notifications.py

"""Подготовка писем подтверждения почты и восстановления пароля."""

from __future__ import annotations

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateError, select_autoescape

from backend.app.core.logging import get_logger
from backend.app.core.paths import TEMPLATES_DIR
from backend.app.core.settings import WebAppSettings
from backend.app.infrastructure.mail.transport import MailTransport

log = get_logger(__name__)

class AuthNotifications:
	"""Рендерить шаблоны только при отправке; не создавать глобальные SMTP-клиенты."""

	def __init__(self, settings: WebAppSettings, transport: MailTransport | None = None) -> None:
		self.settings = settings
		self.transport = transport if transport is not None else MailTransport(settings)
		self.frontend_url = settings.FRONTEND_URL.rstrip("/")
		self.environment = Environment(
			loader=FileSystemLoader(str(TEMPLATES_DIR / "emails")), autoescape=select_autoescape(["html", "xml"]), undefined=StrictUndefined,
		)

	def _render_template(self, template_name: str, context: dict[str, object]) -> str | None:
		try:
			return self.environment.get_template(template_name).render(**context)
		except TemplateError as exc:
			log.error("Не удалось подготовить почтовый шаблон %s. Тип ошибки: %s", template_name, type(exc).__name__)
			return None

	async def send_verification_email(self, user_name: str, user_email: str, verification_token: str) -> bool:
		verification_url = f"{self.frontend_url}/auth/verify-email?token={verification_token}"
		context = {
			"user_name": user_name,
			"user_email": user_email,
			"frontend_url": self.frontend_url,
			"verification_token": verification_token,
			"verification_url": verification_url,
			"support_email": self.settings.MAIL_SUPPORT_EMAIL,
		}
		html = self._render_template("verification_email.html", context)
		if html is None:
			return False

		text = f"Для подтверждения регистрации перейдите по ссылке: {verification_url}"
		return await self.transport.send_email(user_email, "Подтвердите регистрацию в WorldLoom", html, text)

	async def send_password_reset(self, user_email: str, reset_token: str, valid_minutes: int = 30) -> bool:
		context = {
			"user_email": user_email,
			"frontend_url": self.frontend_url,
			"reset_token": reset_token,
			"valid_minutes": valid_minutes,
		}
		html = self._render_template("password_reset.html", context)
		if html is None:
			return False

		reset_url = f"{self.frontend_url}/reset-password?token={reset_token}"
		text = f"Для сброса пароля перейдите по ссылке: {reset_url}"
		return await self.transport.send_email(user_email, "Сброс пароля WorldLoom", html, text)