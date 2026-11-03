# backend/app/modules/catalog/http.py

"""Завершение транзакций каталога и преобразование ожидаемых ошибок в HTTP."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.modules.catalog.errors import CatalogConflict, CatalogNotFound


log = logging.getLogger(__name__)

def _http_error(status_code: int, detail: str) -> HTTPException:
	return HTTPException(status_code=status_code, detail=detail, headers={"Cache-Control": "no-store"})

def _sqlstate(error: IntegrityError) -> str | None:
	original = error.orig
	cause = getattr(original, "__cause__", None)
	return (
			getattr(original, "sqlstate", None)
			or getattr(original, "pgcode", None)
			or getattr(cause, "sqlstate", None)
			or getattr(cause, "pgcode", None)
	)

@asynccontextmanager
async def catalog_operation(session: AsyncSession, *, write: bool = False) -> AsyncIterator[None]:
	try:
		yield

		if write:
			await session.commit()
		else:
			await session.rollback()
	except CatalogNotFound as exc:
		await session.rollback()
		raise _http_error(404, str(exc)) from None
	except CatalogConflict as exc:
		await session.rollback()
		raise _http_error(409, str(exc)) from None
	except IntegrityError as exc:
		await session.rollback()
		code = _sqlstate(exc)

		if code == "23505":
			raise _http_error(409, "Игровая система с таким названием или slug уже существует.") from None

		if code == "23503":
			raise _http_error(409, "Изменение конфликтует со связанными данными.") from None

		log.exception("Неизвестное нарушение ограничений при изменении каталога.")
		raise _http_error(500, "Не удалось сохранить карточку игровой системы.") from None
	except BaseException:
		await session.rollback()
		raise