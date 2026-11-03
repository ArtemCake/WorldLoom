# backend/app/infrastructure/mail/transport.py

"""Асинхронная отправка почты через основной и резервный SMTP."""

from __future__ import annotations

import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formataddr

from aiosmtplib import SMTP

from backend.app.core.logging import get_logger
from backend.app.core.settings import WebAppSettings

log = get_logger(__name__)

@dataclass(frozen=True)
class SMTPConfig:
	host: str
	port: int
	username: str
	password: str = field(repr=False)
	use_tls: bool
	use_ssl: bool
	sender_email: str

class MailTransport:
	"""Не открывает соединения при создании; отдельное соединение на отправку."""

	def __init__(self, settings: WebAppSettings) -> None:
		self.sender_name = settings.MAIL_SENDER_NAME
		self.primary = SMTPConfig(
			host=settings.SMTP_HOST, port=settings.SMTP_PORT, username=settings.SMTP_USER, password=settings.SMTP_PASSWORD,
			use_tls=settings.SMTP_USE_TLS, use_ssl=settings.SMTP_USE_SSL, sender_email=settings.MAIL_SENDER_EMAIL,
		)
		self.fallback: SMTPConfig | None = None

		if settings.SMTP_FALLBACK_HOST:
			if settings.SMTP_FALLBACK_PORT is None:
				raise ValueError("Для резервного SMTP требуется SMTP_FALLBACK_PORT")

			fallback_sender = settings.MAIL_FALLBACK_SENDER_EMAIL or settings.SMTP_FALLBACK_USER or settings.MAIL_SENDER_EMAIL
			self.fallback = SMTPConfig(
				host=settings.SMTP_FALLBACK_HOST, port=settings.SMTP_FALLBACK_PORT, username=settings.SMTP_FALLBACK_USER or "",
				password=settings.SMTP_FALLBACK_PASSWORD or "", use_tls=settings.SMTP_FALLBACK_USE_TLS,
				use_ssl=settings.SMTP_FALLBACK_USE_SSL, sender_email=fallback_sender,
			)

		for configuration in (self.primary, self.fallback):
			if configuration is None:
				continue
			if configuration.use_tls and configuration.use_ssl:
				raise ValueError("SMTP_USE_TLS и SMTP_USE_SSL не должны одновременно включаться для одного сервера")

	async def _try_send(self, message: EmailMessage, recipients: list[str], configuration: SMTPConfig) -> bool:
		"""Отправить письмо; частичный отказ получателей не считать полным успехом."""
		if "From" in message:
			del message["From"]

		message["From"] = formataddr((self.sender_name, configuration.sender_email))
		smtp = SMTP(
			hostname=configuration.host, port=configuration.port, use_tls=configuration.use_ssl, start_tls=False,
			validate_certs=True, tls_context=ssl.create_default_context(), timeout=30,
		)

		try:
			await smtp.connect()

			if configuration.use_tls and not configuration.use_ssl:
				await smtp.starttls()

			if configuration.username and configuration.password:
				await smtp.login(configuration.username, configuration.password)

			refused, _ = await smtp.send_message(message, sender=configuration.sender_email, recipients=recipients)
			if refused:
				log.warning("SMTP принял письмо не для всех получателей.")
				return False

			return True
		finally:
			try:
				if smtp.is_connected:
					await smtp.quit()
			except Exception:
				smtp.close()

	async def send_email(
			self, to_email: str, subject: str, html_content: str, text_content: str | None = None,
			cc: list[str] | None = None, bcc: list[str] | None = None,
	) -> bool:
		"""Вернуть результат передачи SMTP-серверу, а не подтверждение доставки в почтовый ящик."""
		message = EmailMessage()
		message["Subject"] = subject
		message["To"] = to_email

		if cc:
			message["Cc"] = ", ".join(cc)

		message.set_content(text_content or "Это HTML-письмо. Откройте его в почтовом клиенте с поддержкой HTML.")
		message.add_alternative(html_content, subtype="html")
		recipients = list(dict.fromkeys([to_email, *(cc or []), *(bcc or [])]))

		try:
			return await self._try_send(message, recipients, self.primary)
		except Exception as exc:
			log.error("Основной SMTP не подтвердил отправку. Тип ошибки: %s", type(exc).__name__)

		if self.fallback is None:
			return False

		try:
			return await self._try_send(message, recipients, self.fallback)
		except Exception as exc:
			log.error("Резервный SMTP не подтвердил отправку. Тип ошибки: %s", type(exc).__name__)
			return False

	async def send_system_alert(self, subject: str, html_body: str, admin_emails: list[str]) -> bool:
		"""Попытаться отправить уведомление каждому из указанных администраторов."""
		success = True
		for email in admin_emails:
			if not await self.send_email(email, subject, html_body):
				success = False
		return success