# backend/app/modules/rules/http.py

"""HTTP-зависимости, транзакции и безопасные ответы модуля правил."""

from __future__ import annotations
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from fastapi import Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from fastapi_csrf_protect.exceptions import CsrfProtectError
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse
from backend.app.infrastructure.database.session import get_async_session
from backend.app.modules.admin.dependencies import require_content_manager
from backend.app.modules.auth.dependencies import get_current_user
from backend.app.modules.rules import errors
from backend.app.modules.rules.schemas.catalog import CatalogQuery
from backend.app.modules.users.models.user import User


logger = logging.getLogger(__name__)

RulesSession = Annotated[AsyncSession, Depends(get_async_session)]
RulesUser = Annotated[User, Depends(get_current_user)]
RulesEditor = Annotated[User, Depends(require_content_manager)]

class HttpCatalogQuery(CatalogQuery):
	"""Преобразовать строковый HTTP-параметр limit в число."""

	limit: int = Field(default=30, ge=1, le=100)

def _error_response(status_code: int, detail: str) -> JSONResponse:
	return JSONResponse(status_code=status_code, content={"detail": detail})

class RulesRoute(APIRoute):
	"""Не раскрывать внутренние исключения и не кешировать ответы."""

	def get_route_handler(self):
		original = super().get_route_handler()

		async def handler(request: Request):
			try:
				response = await original(request)
			except RequestValidationError:
				response = _error_response(422, "Некорректные параметры запроса")
			except CsrfProtectError:
				response = _error_response(403, "Не удалось подтвердить защиту запроса")
			except HTTPException as exc:
				response = JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)
			except (errors.RuleArticleNotFound, errors.RuleBookNotFound):
				response = _error_response(404, "Материал или публикация не найдены")
			except (errors.RuleArticleConflict, errors.RuleBookConflict):
				response = _error_response(409, "Операция конфликтует с текущим состоянием материала")
			except (errors.InvalidRuleArticle, errors.InvalidRuleBook):
				response = _error_response(422, "Некорректные данные материала")
			except Exception:
				logger.error("Не удалось выполнить HTTP-операцию модуля правил")
				response = _error_response(500, "Не удалось выполнить операцию с правилами")

			response.headers["Cache-Control"] = "no-store"
			return response

		return handler

@asynccontextmanager
async def rules_operation(session: AsyncSession, *, write: bool = False) -> AsyncIterator[None]:
	"""Завершить транзакцию HTTP-запроса, включая открытую авторизацией."""
	try:
		if session.new or session.dirty or session.deleted:
			raise RuntimeError("Операция требует сессию без ожидающих ORM-изменений")

		if session.in_nested_transaction():
			raise RuntimeError("HTTP-операция не должна выполняться во вложенной транзакции")

		if not session.in_transaction():
			await session.begin()

		yield

		if write:
			await session.commit()
		else:
			await session.rollback()
	except BaseException:
		await session.rollback()
		raise
