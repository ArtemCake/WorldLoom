# backend/app/web/exception_handlers.py

"""Преобразование ожидаемых ошибок модулей в безопасные HTTP-ответы."""

from __future__ import annotations
import logging
from collections.abc import Callable, Coroutine
from typing import Any
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from fastapi_csrf_protect.exceptions import CsrfProtectError
from backend.app.modules.games import errors as game_errors
from backend.app.modules.maps import errors
from backend.app.web.error_responses import adapt_domain_error


log = logging.getLogger(__name__)
RequestHandler = Callable[[Request], Coroutine[Any, Any, Response]]

EXPECTED_MAP_ERRORS = (
	errors.MapOperationError,
	errors.MapStorageError,
	errors.MapImageError,
	CsrfProtectError,
)

EXPECTED_GAME_ERRORS = (
	game_errors.GameOperationError,
	game_errors.GameDeletionError,
	CsrfProtectError,
)


def map_error_response(error: Exception) -> JSONResponse:
	"""Вернуть предметный отказ без раскрытия внутренних путей."""
	status_code = 500
	code = "map_operation_failed"
	detail = "Не удалось выполнить операцию с картой."

	if isinstance(error, CsrfProtectError):
		status_code = 403
		code = "csrf_rejected"
		detail = "Не удалось проверить защиту запроса. Обновите страницу."
	elif isinstance(error, errors.MapCommitOutcomeUnknown):
		status_code = 503
		code = "map_commit_unknown"
		detail = "Результат сохранения не подтверждён. Проверьте состояние карты перед повтором."
	elif isinstance(error, (errors.MapAccessDenied, errors.MapStorageForbidden)):
		status_code = 403
		code = "map_access_denied"
		detail = str(error)
	elif isinstance(error, (errors.MapEntityNotFound, errors.MapStorageNotFound, errors.MapImageNotFound)):
		status_code = 404
		code = "map_not_found"
		detail = str(error)
	elif isinstance(error, (errors.MapStateConflict, errors.MapStorageConflict)):
		status_code = 409
		code = "map_state_conflict"
		detail = str(error)
	elif isinstance(error, errors.MapImageTooLarge):
		status_code = 413
		code = "map_image_too_large"
		detail = str(error)
	elif isinstance(error, (errors.InvalidMapOperation, errors.InvalidMapStorage, errors.InvalidMapImage)):
		status_code = 422
		code = "invalid_map_input"
		detail = str(error)

	if status_code >= 500:
		log.error("Операция с картой завершилась отказом. Тип ошибки: %s", type(error).__name__)

	return JSONResponse(
		status_code=status_code,
		content={"detail": detail, "code": code},
		headers={"Cache-Control": "no-store"},
	)

def game_error_response(error: Exception) -> JSONResponse:
	"""Преобразовать известные ошибки лобби и удаления игр."""
	status_code = 500
	code = "game_operation_failed"
	detail = "Не удалось выполнить операцию с игрой."

	if isinstance(error, CsrfProtectError):
		status_code = 403
		code = "csrf_rejected"
		detail = "Не удалось проверить защиту запроса. Обновите страницу."
	elif isinstance(error, game_errors.GameCommitOutcomeUnknown):
		status_code = 503
		code = "game_commit_unknown"
		detail = "Результат сохранения не подтверждён. Проверьте состояние игры перед повтором."
	elif isinstance(error, (game_errors.GameAccessDenied, game_errors.GameDeletionForbidden)):
		status_code = 403
		code = "game_access_denied"
		detail = str(error)
	elif isinstance(error, game_errors.InviteExpired):
		status_code = 410
		code = "invite_expired"
		detail = str(error)
	elif isinstance(error, (game_errors.GameStateConflict, game_errors.GameDeletionConflict)):
		status_code = 409
		code = "game_state_conflict"
		detail = str(error)
	elif isinstance(error, (game_errors.InvalidGameInput, game_errors.InvalidGameDeletion)):
		status_code = 422
		code = "invalid_game_input"
		detail = str(error)
	elif isinstance(
			error,
			(
					game_errors.GameNotFound,
					game_errors.GameSessionNotFound,
					game_errors.GameSystemNotFound,
					game_errors.PartyMemberNotFound,
					game_errors.InviteNotFound,
					game_errors.GameCleanupJobNotFound,
			),
	):
		status_code = 404
		code = "game_entity_not_found"
		detail = str(error)

	if status_code >= 500:
		log.error("Операция с игрой завершилась отказом. Тип ошибки: %s", type(error).__name__)

	return JSONResponse(
		status_code=status_code,
		content={"detail": detail, "code": code},
		headers={"Cache-Control": "no-store"},
	)

class MapErrorRoute(APIRoute):
	"""Обработать ожидаемые отказы карт внутри HTTP-границы."""

	def get_route_handler(self) -> RequestHandler:
		original_handler = super().get_route_handler()

		async def handler(request: Request) -> Response:
			try:
				return await original_handler(request)
			except EXPECTED_MAP_ERRORS as error:
				return adapt_domain_error(request, map_error_response(error))

		return handler

class GameErrorRoute(APIRoute):
	"""Обработать ожидаемые отказы игр внутри HTTP-границы."""

	def get_route_handler(self) -> RequestHandler:
		original_handler = super().get_route_handler()

		async def handler(request: Request) -> Response:
			try:
				return await original_handler(request)
			except EXPECTED_GAME_ERRORS as error:
				return adapt_domain_error(request, game_error_response(error))

		return handler
