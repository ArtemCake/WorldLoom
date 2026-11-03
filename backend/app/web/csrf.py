# backend/app/web/csrf.py

"""Адаптер CSRF для HTML-страниц и изменяющих запросов.

Рассчитан на fastapi-csrf-protect 1.0.7.
Конфигурация библиотеки подключается при сборке приложения.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from fastapi import Depends, Request
from fastapi_csrf_protect import CsrfProtect
from itsdangerous import BadData, URLSafeTimedSerializer
from starlette.responses import Response


_CSRF_SALT = "fastapi-csrf-token"
_REQUEST_STATE_KEY = "_worldloom_csrf_page_tokens"


@dataclass(frozen=True)
class CsrfPageTokens:
	"""Данные CSRF для выдачи HTML.

	Подписанный токен присутствует только при создании новой пары.
	"""

	token: str = field(repr=False)
	signed_token: str | None = field(default=None, repr=False)

def ensure_csrf_tokens(request: Request, csrf_protect: CsrfProtect) -> CsrfPageTokens:
	"""Переиспользовать действующую cookie или создать новую пару."""
	cached = getattr(request.state, _REQUEST_STATE_KEY, None)

	if isinstance(cached, CsrfPageTokens):
		return cached

	# В версии 1.0.7 извлечение исходного токена из cookie
	# требует доступа к внутренним настройкам библиотеки.
	# Этот доступ сосредоточен в одном адаптере.
	secret_key = csrf_protect._secret_key

	if secret_key is None:
		raise RuntimeError(
			"Для работы CSRF необходимо настроить secret_key"
		)

	signed_cookie = request.cookies.get(
		csrf_protect._cookie_key
	)

	if signed_cookie:
		serializer = URLSafeTimedSerializer(
			secret_key,
			salt=_CSRF_SALT,
		)

		try:
			token = serializer.loads(
				signed_cookie,
				max_age=csrf_protect._max_age,
			)
		except BadData:
			pass
		else:
			if isinstance(token, str) and token:
				tokens = CsrfPageTokens(token=token)
				setattr(request.state, _REQUEST_STATE_KEY, tokens)
				return tokens

	token, signed_token = csrf_protect.generate_csrf_tokens()

	tokens = CsrfPageTokens(
		token=token,
		signed_token=signed_token,
	)
	setattr(request.state, _REQUEST_STATE_KEY, tokens)

	return tokens

def apply_csrf_tokens(response: Response, csrf_protect: CsrfProtect, tokens: CsrfPageTokens) -> None:
	"""Добавить токены именно в возвращаемый браузеру ответ."""
	if tokens.signed_token is not None:
		csrf_protect.set_csrf_cookie(
			tokens.signed_token,
			response,
		)

	response.headers["X-CSRF-Token"] = tokens.token
	response.headers["Cache-Control"] = "no-store"

async def enforce_csrf(request: Request, csrf_protect: CsrfProtect = Depends()) -> None:
	"""Проверить CSRF на изменяющем маршруте."""
	await csrf_protect.validate_csrf(request)