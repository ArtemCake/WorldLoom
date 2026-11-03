# backend/app/web/middleware.py

"""ASGI-middleware защитных заголовков и его явное подключение."""

from __future__ import annotations
from fastapi import FastAPI
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from backend.app.web.security_headers import build_security_headers


class SecurityHeadersMiddleware:
	"""Добавить защитные заголовки, не буферизуя тело ответа."""

	def __init__(self, app: ASGIApp, *, production: bool = False) -> None:
		self.app = app
		self._headers = build_security_headers(production=production)

	async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
		if scope["type"] != "http":
			await self.app(scope, receive, send)
			return

		async def send_with_security_headers(message: Message) -> None:
			if message["type"] == "http.response.start":
				headers = MutableHeaders(scope=message)

				for name, value in self._headers.items():
					headers[name] = value

			await send(message)

		await self.app(scope, receive, send_with_security_headers)

def install_security_middleware(app: FastAPI, *, production: bool = False) -> None:
	"""Подключить middleware один раз, до запуска приложения."""
	if app.middleware_stack is not None:
		raise RuntimeError("Защитные заголовки нужно подключать до запуска приложения")

	if any(middleware.cls is SecurityHeadersMiddleware for middleware in app.user_middleware):
		raise RuntimeError("Middleware защитных заголовков уже подключён")

	app.add_middleware(SecurityHeadersMiddleware, production=production)
