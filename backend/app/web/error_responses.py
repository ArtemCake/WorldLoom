# backend/app/web/error_responses.py

"""Выбор HTML- или JSON-ответа без обращения к БД и шаблонам."""

from __future__ import annotations
import json
from collections.abc import Mapping
from html import escape
from typing import Any
from fastapi.encoders import jsonable_encoder
from fastapi.routing import APIRoute
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
import logging


log = logging.getLogger(__name__)

def _accept_quality(request: Request, media_type: str) -> float:
	"""Прочитать явно указанный тип содержимого из Accept."""
	quality = 0.0

	for item in request.headers.get("accept", "").lower().split(","):
		parts = [part.strip() for part in item.split(";")]
		current_type = parts[0]

		if current_type != media_type:
			if media_type != "application/json" or not current_type.startswith("application/") or not current_type.endswith("+json"):
				continue

		current_quality = 1.0

		for parameter in parts[1:]:
			key, separator, value = parameter.partition("=")

			if separator and key.strip() == "q":
				try:
					current_quality = float(value.strip())
				except ValueError:
					current_quality = 0.0

		if 0.0 < current_quality <= 1.0:
			quality = max(quality, current_quality)

	return quality

def wants_html_error(request: Request) -> bool:
	"""Сохранить JSON для API, а для страниц выбрать HTML."""
	route = request.scope.get("route")
	html_quality = _accept_quality(request, "text/html")
	json_quality = _accept_quality(request, "application/json")

	if isinstance(route, APIRoute):
		response_class = getattr(route.response_class, "value", route.response_class)
		html_route = isinstance(response_class, type) and issubclass(response_class, HTMLResponse)

		if not html_route:
			return False

		if json_quality > 0 and json_quality >= html_quality:
			return False

		return True

	return html_quality > 0 and html_quality > json_quality

def _response_headers(headers: Mapping[str, str] | None) -> dict[str, str]:
	"""Сохранить служебные заголовки, пересчитав заголовки тела."""
	result = {
		name.lower(): value
		for name, value in (headers or {}).items()
		if name.lower() not in {"content-length", "content-type"}
	}
	result["cache-control"] = "no-store"
	vary = [value.strip() for value in result.get("vary", "").split(",") if value.strip()]

	if "*" not in vary and not any(value.lower() == "accept" for value in vary):
		vary.append("Accept")

	result["vary"] = ", ".join(vary)
	return result

def build_error_response(request: Request, status_code: int, detail: Any, *, code: str | None = None,
		headers: Mapping[str, str] | None = None) -> Response:
	"""Собрать HTML- или JSON-ответ без обращения к БД."""
	response_headers = _response_headers(headers)

	if wants_html_error(request):
		titles = {
			400: "Некорректный запрос",
			401: "Необходим вход",
			403: "Доступ запрещён",
			404: "Страница не найдена",
			405: "Метод не поддерживается",
			409: "Состояние данных изменилось",
			410: "Ресурс больше недоступен",
			413: "Слишком большой запрос",
			422: "Проверьте данные",
			429: "Слишком много запросов",
			500: "Ошибка приложения",
			503: "Операция временно недоступна",
		}

		title = titles.get(
			status_code,
			"Не удалось выполнить запрос",
		)

		text = (
			detail
			if isinstance(detail, str)
			else "Проверьте данные запроса и повторите действие."
		)

		# Резервный HTML готовим заранее.
		# Он не зависит от шаблонов, настроек и подключения к БД.
		content = (
			'<!doctype html>'
			'<html lang="ru">'
			'<head>'
			'<meta charset="utf-8">'
			'<meta name="viewport" '
			'content="width=device-width, initial-scale=1">'
			f'<title>{status_code} — {escape(title)}</title>'
			'</head>'
			'<body>'
			'<main>'
			f'<h1>{status_code} — {escape(title)}</h1>'
			f'<p>{escape(text)}</p>'
			'<p><a href="/">На главную</a></p>'
			'</main>'
			'</body>'
			'</html>'
		)

		try:
			templates = getattr(
				request.app.state,
				"templates",
				None,
			)

			settings = getattr(
				request.app.state,
				"settings",
				None,
			)

			if templates is None:
				raise RuntimeError(
					"HTML-шаблоны не подключены"
				)

			response = templates.TemplateResponse(
				request=request,
				name="errors/not_found.html",
				context={
					"request": request,
					"project_name": getattr(
						settings,
						"PROJECT_NAME",
						"WorldLoom",
					),
					"user": None,
					"csrf_token": "",
					"error_status": status_code,
					"error_title": title,
					"error_text": text,
				},
				status_code=status_code,
				headers=response_headers,
			)

		except Exception:
			log.exception(
				"Не удалось сформировать страницу ошибки %s",
				status_code,
			)

			response = HTMLResponse(
				content=content,
				status_code=status_code,
				headers=response_headers,
			)

	else:
		payload = {
			"detail": jsonable_encoder(detail),
		}

		if code is not None:
			payload["code"] = code

		response = JSONResponse(
			content=payload,
			status_code=status_code,
			headers=response_headers,
		)

	if request.method == "HEAD":
		return Response(
			status_code=status_code,
			headers=dict(response.headers),
		)

	return response

def adapt_domain_error(request: Request, response: JSONResponse) -> Response:
	"""Адаптировать уже подготовленный предметный отказ для HTML-страницы."""
	if not wants_html_error(request):
		return response

	payload = json.loads(response.body)
	return build_error_response(
		request, response.status_code, payload["detail"],
		code=payload.get("code"), headers=response.headers,
	)