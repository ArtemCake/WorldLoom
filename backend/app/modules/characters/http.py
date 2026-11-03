# backend/app/modules/characters/http.py

"""Управление транзакциями персонажей и преобразование ошибок в HTTP."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from fastapi import HTTPException
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError
from backend.app.modules.characters.errors import (CharacterAccessDenied, CharacterError, CharacterNotFound, CharacterStateConflict,
                                                   CharacterStateNotInitialized, CharacterStateStorageError, InvalidCharacterStateChange)


log = logging.getLogger(__name__)

def _http_error(status_code: int, detail: str) -> HTTPException:
	return HTTPException(status_code=status_code, detail=detail, headers={"Cache-Control": "no-store"})

def _character_http_error(error: CharacterError) -> HTTPException:
	if isinstance(error, CharacterNotFound):
		return _http_error(404, "Персонаж, игровой лист или публикация правил не найдены.")

	if isinstance(error, CharacterAccessDenied):
		return _http_error(403, "Операция недоступна для текущего пользователя или участия в игре.")

	if isinstance(error, CharacterStateNotInitialized):
		return _http_error(409, "Запись ещё не переведена на универсальное состояние персонажа.")

	if isinstance(error, CharacterStateConflict):
		return _http_error(409, "Данные изменились или не соответствуют закреплённым правилам. Получите актуальное состояние.")

	if isinstance(error, InvalidCharacterStateChange):
		return _http_error(422, "Переданные значения не соответствуют закреплённым правилам.")

	if isinstance(error, CharacterStateStorageError):
		return _http_error(500, "Не удалось прочитать сохранённое состояние персонажа или правила.")

	return _http_error(500, "Не удалось выполнить операцию с персонажем.")

def _sqlstate(error: DBAPIError) -> str | None:
	original = error.orig
	cause = getattr(original, "__cause__", None)
	return (
			getattr(original, "sqlstate", None)
			or getattr(original, "pgcode", None)
			or getattr(cause, "sqlstate", None)
			or getattr(cause, "pgcode", None)
	)

@asynccontextmanager
async def character_operation(session: AsyncSession, *, write: bool = False) -> AsyncIterator[None]:
	"""Завершить транзакцию до возврата успешного ответа."""
	try:
		yield

		if write:
			await session.commit()
		else:
			await session.rollback()
	except CharacterError as exc:
		await session.rollback()
		error = _character_http_error(exc)

		if error.status_code >= 500:
			log.error("Ошибка состояния персонажа: %s", type(exc).__name__)

		raise error from exc
	except StaleDataError as exc:
		await session.rollback()
		raise _http_error(409, "Запись изменена или удалена другой операцией. Получите актуальные данные.") from exc
	except IntegrityError as exc:
		await session.rollback()
		code = _sqlstate(exc)

		if code in {"23503", "23505"}:
			raise _http_error(409, "Операция конфликтует со связанными или уже существующими данными.") from exc

		log.error("Нарушение ограничений при операции персонажа: %s", type(exc).__name__)
		raise _http_error(500, "Не удалось сохранить данные персонажа.") from exc
	except DBAPIError as exc:
		await session.rollback()

		if _sqlstate(exc) in {"40001", "40P01", "55P03"}:
			raise _http_error(409, "Конфликт одновременных операций. Получите актуальные данные перед повтором.") from exc

		log.error("Ошибка базы данных при операции персонажа: %s", type(exc).__name__)
		raise _http_error(500, "Не удалось завершить операцию с персонажем.") from exc
	except BaseException:
		await session.rollback()
		raise