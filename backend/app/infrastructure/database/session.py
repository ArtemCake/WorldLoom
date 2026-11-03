# backend/app/infrastructure/database/session.py

"""Асинхронный движок и управление сессиями базы данных.

Импорт модуля не загружает настройки и не создаёт движок.
Фиксацией транзакций управляет вызывающий прикладной код.
"""

from __future__ import annotations
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from sqlalchemy import text
from sqlalchemy.engine import URL
from fastapi import Request
from sqlalchemy.ext.asyncio import (AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine)


POOL_SIZE = 10
MAX_OVERFLOW = 20


class Database:
	"""Владелец движка и фабрики асинхронных сессий.

	Один экземпляр создаётся на процесс приложения.

	Один AsyncSession нельзя одновременно использовать
	в нескольких задачах.
	"""

	def __init__(self, database_url: str | URL, *, pool_size: int = POOL_SIZE, max_overflow: int = MAX_OVERFLOW) -> None:
		self._engine = create_async_engine(
			database_url,
			echo=False,
			echo_pool=False,
			hide_parameters=True,
			pool_size=pool_size,
			max_overflow=max_overflow,
			pool_pre_ping=True,
		)

		self._session_factory = async_sessionmaker(
			bind=self._engine,
			class_=AsyncSession,
			expire_on_commit=False,
		)

	@property
	def engine(self) -> AsyncEngine:
		"""Движок для инфраструктурных операций."""
		return self._engine

	@property
	def session_factory(self) -> async_sessionmaker[AsyncSession]:
		"""Фабрика для компонентов с собственным циклом сессий.

		Получатель обязан сам закрывать созданные сессии.
		Например, использовать async with session_factory().
		"""
		return self._session_factory

	@asynccontextmanager
	async def session(self) -> AsyncIterator[AsyncSession]:
		"""Предоставить отдельную сессию и обеспечить её закрытие.

		При исключении, включая отмену задачи, явно запрашивает
		rollback и передаёт исключение дальше.

		При обычном выходе не выполняет commit.
		Незавершённую транзакцию освобождает закрытие сессии.
		"""
		async with self._session_factory() as session:
			try:
				yield session
			except BaseException:
				await session.rollback()
				raise

	async def check_connection(self) -> None:
		"""Проверить возможность подключения и выполнения SELECT 1.

		Не проверяет полноту схемы и актуальность миграций.
		"""
		async with self._engine.connect() as connection:
			await connection.execute(text("SELECT 1"))

	async def dispose(self) -> None:
		"""Освободить пул после завершения пользователей БД.

		Не заменяет закрытие активных сессий.
		После вызова приложение не должно создавать новые сессии
		через этот экземпляр.
		"""
		await self._engine.dispose()

async def get_async_session(request: Request) -> AsyncIterator[AsyncSession]:
	"""Предоставить сессию для одного HTTP-запроса.

	Database создаётся при сборке приложения.
	Зависимость не создаёт движок и не выполняет commit.
	"""
	database = getattr(request.app.state, "database", None)

	if not isinstance(database, Database):
		raise RuntimeError(
			"База данных не подключена к состоянию приложения"
		)

	async with database.session() as session:
		yield session
