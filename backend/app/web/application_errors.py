# backend/app/web/application_errors.py

"""Глобальные HTTP-ошибки, валидация и безопасный ответ при сбое."""

from __future__ import annotations
import logging
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi_csrf_protect.exceptions import CsrfProtectError
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import Response
from backend.app.web.error_responses import build_error_response


log = logging.getLogger(__name__)

FIELD_NAMES = {
	"email": "Email",
	"password": "Пароль",
	"nickname": "Никнейм",
	"old_password": "Текущий пароль",
	"new_password": "Новый пароль",
}

def _validation_detail(error: RequestValidationError) -> str:
	"""Сформировать описание без значений ошибочных полей."""
	missing = []

	for item in error.errors():
		location = item.get("loc", ())

		if item.get("type") != "missing" or not location:
			continue

		label = FIELD_NAMES.get(str(location[-1]))

		if label is not None and label not in missing:
			missing.append(label)

	if missing:
		return "Не заполнены обязательные поля: " + ", ".join(missing)

	return "Некорректные данные в запросе. Проверьте правильность заполнения формы."

async def http_error_handler(request: Request, error: HTTPException) -> Response:
	"""Обработать HTTP-отказ, сохранив публичные детали ожидаемых ошибок."""
	if error.status_code in {204, 304} or 100 <= error.status_code < 200:
		return Response(status_code=error.status_code, headers=error.headers)

	detail = error.detail

	if error.status_code >= 500:
		detail = "Не удалось выполнить запрос. Внутренняя ошибка приложения."

	return build_error_response(request, error.status_code, detail, headers=error.headers)

async def validation_error_handler(request: Request, error: RequestValidationError) -> Response:
	"""Вернуть 422, не публикуя исходные значения и контекст проверки."""
	detail = _validation_detail(error)

	if request.url.path.startswith("/admin/game-systems/"):
		detail = [
			{
				"type": item.get("type", "validation_error"),
				"loc": list(item.get("loc", ())),
				"msg": "Обязательное поле отсутствует" if item.get("type") == "missing" else "Некорректное значение",
			}
			for item in error.errors()
		]

	return build_error_response(request, 422, detail)

async def csrf_error_handler(request: Request, error: CsrfProtectError) -> Response:
	"""Не передавать браузеру внутренние подробности проверки CSRF."""
	return build_error_response(
		request, 403, "Не удалось проверить защиту запроса. Обновите страницу.",
		code="csrf_rejected",
	)

async def unhandled_error_handler(request: Request, error: Exception) -> Response:
	"""Не раскрывать traceback, SQL, настройки и содержимое запроса."""
	log.error("Необработанная ошибка приложения. Тип: %s", type(error).__name__)

	return build_error_response(
		request, 500, "Не удалось выполнить запрос. Внутренняя ошибка приложения.",
		code="internal_error",
	)

def install_exception_handlers(app: FastAPI) -> None:
	"""Зарегистрировать общую политику ошибок до запуска приложения."""
	if app.middleware_stack is not None:
		raise RuntimeError("Обработчики ошибок нужно подключать до запуска приложения")

	if app.debug:
		raise RuntimeError("Для безопасных ответов об ошибках создайте FastAPI с debug=False")

	if getattr(app.state, "_application_errors_installed", False):
		raise RuntimeError("Глобальные обработчики ошибок уже подключены")

	app.add_exception_handler(HTTPException, http_error_handler)
	app.add_exception_handler(404, http_error_handler)
	app.add_exception_handler(RequestValidationError, validation_error_handler)
	app.add_exception_handler(CsrfProtectError, csrf_error_handler)
	app.add_exception_handler(Exception, unhandled_error_handler)
	app.add_exception_handler(500, unhandled_error_handler)
	app.state._application_errors_installed = True