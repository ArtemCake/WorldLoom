# backend/app/modules/users/http.py

"""Преобразование ожидаемых ошибок профиля в HTTP-ответы."""

from fastapi import Request
from fastapi.routing import APIRoute
from fastapi_csrf_protect.exceptions import CsrfProtectError
from starlette.responses import JSONResponse, Response
from backend.app.modules.auth.errors import AuthError
from backend.app.modules.auth.http import RequestHandler, auth_error_response
from backend.app.modules.users.errors import AvatarTooLarge, CurrentPasswordInvalid, ProfileConflict, ProfileError, ProfileSessionExpired


class ProfileRoute(APIRoute):
	"""Сохранить понятные ответы и запретить кеширование персональных данных."""

	def get_route_handler(self) -> RequestHandler:
		original_handler = super().get_route_handler()

		async def route_handler(request: Request) -> Response:
			try:
				response = await original_handler(request)
			except ProfileError as exc:
				if isinstance(exc, (ProfileSessionExpired, CurrentPasswordInvalid)):
					status_code = 401
				elif isinstance(exc, ProfileConflict):
					status_code = 409
				elif isinstance(exc, AvatarTooLarge):
					status_code = 413
				else:
					status_code = 400
				response = JSONResponse(status_code=status_code, content={"detail": exc.message})
			except AuthError as exc:
				response = auth_error_response(exc)
			except CsrfProtectError:
				response = JSONResponse(
					status_code=403, content={"detail": "Не удалось проверить защиту запроса. Обновите страницу и попробуйте снова."},
				)

			response.headers["Cache-Control"] = "no-store"
			response.headers["Referrer-Policy"] = "no-referrer"
			return response

		return route_handler