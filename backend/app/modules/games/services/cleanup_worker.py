# backend/app/modules/games/services/cleanup_worker.py

"""Повторная обработка сохранённых заданий очистки игр и карт.

Импорт не запускает задачи и не открывает соединения.
Предметные проверки и файловое удаление остаются в сервисах.

Для фоновой обработки каждого задания используется отдельная
сессия и транзакция. Заблокированные задания пропускаются.
Игры и карты имеют независимые циклы и позиции обхода.
"""

from __future__ import annotations
import asyncio
import logging
import math
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.modules.games.models.lobby import GameDeletionJob
from backend.app.modules.games.services import game_deletion_service
from backend.app.modules.maps.models import MapDeletionJob
from backend.app.modules.maps.services import map_cleanup_service
from backend.app.modules.maps.services import map_management_service as management


log = logging.getLogger(__name__)
_JOBS = GameDeletionJob.__table__
SessionFactory = Callable[[], AsyncSession]
SessionProvider = Callable[[], AbstractAsyncContextManager[AsyncSession]]

def _require_positive_integer(value: int, label: str) -> None:
	if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
		raise ValueError(f"Требуется положительное целое число: {label}")

async def _wait_until_finished(task: asyncio.Task[None]) -> None:
	"""Передать внешнюю отмену после завершения защищённой операции."""
	cancelled = False

	while True:
		try:
			await asyncio.shield(task)
			break
		except asyncio.CancelledError:
			if task.cancelled():
				raise

			cancelled = True

	if cancelled:
		raise asyncio.CancelledError()

async def _execute_cleanup(plan: dict[str, Any], root: Path) -> None:
	"""Не освобождать транзакцию, пока файловый поток не завершился."""
	task = asyncio.create_task(asyncio.to_thread(map_cleanup_service.execute_plan, plan, root=root))
	await _wait_until_finished(task)

async def finish_cleanup_job(session_factory: SessionFactory, game_id: UUID, master_id: UUID, *, root: Path) -> None:
	"""Сохранённый интерфейс обработки одной игры с проверкой её владельца."""

	async def finish() -> None:
		async with session_factory() as session:
			async with session.begin():
				await game_deletion_service.finish_cleanup(session, game_id, master_id, _execute_cleanup, root=root)

	await _wait_until_finished(asyncio.create_task(finish()))

async def process_cleanup_batch(session_factory: SessionFactory, *, root: Path, batch_size: int = 100) -> int:
	"""Сохранённый интерфейс разовой обработки начальной порции игр.

	Для постоянного обхода используется GameCleanupWorker.
	Повторные отдельные вызовы этой функции не сохраняют позицию обхода.
	"""
	_require_positive_integer(batch_size, "размер пакета")

	async with session_factory() as session:
		async with session.begin():
			result = await session.execute(
				select(_JOBS.c.game_id, _JOBS.c.master_id)
				.where(_JOBS.c.cleanup_complete.is_(False))
				.order_by(_JOBS.c.created_at, _JOBS.c.game_id)
				.limit(batch_size)
			)
			pending = [(row.game_id, row.master_id) for row in result.all()]

	completed = 0

	for game_id, master_id in pending:
		try:
			await finish_cleanup_job(session_factory, game_id, master_id, root=root)
		except asyncio.CancelledError:
			raise
		except Exception as error:
			log.error("Не удалось завершить очистку игры %s. Тип ошибки: %s", game_id, type(error).__name__)
		else:
			completed += 1

	return completed

async def run_cleanup_worker(session_factory: SessionFactory, *, root: Path, interval_seconds: int = 60, batch_size: int = 100) -> None:
	"""Сохранённый интерфейс постоянной обработки игр до отмены вызывающей задачи."""
	_require_positive_integer(interval_seconds, "интервал повторной обработки")
	_require_positive_integer(batch_size, "размер пакета")
	worker = GameCleanupWorker(session_factory, root=root, interval_seconds=interval_seconds, batch_size=batch_size)
	worker.start()

	try:
		await worker.wait()
	finally:
		await worker.aclose()

@dataclass(frozen=True, slots=True)
class CleanupBatchResult:
	"""Статистика выбранной порции, а не состояние всей очереди."""

	selected: int = 0
	completed: int = 0
	skipped: int = 0
	failed: int = 0

class _CleanupQueue:
	"""Общий цикл очереди; конкретный обработчик задаёт таблицу и исполнение."""

	job_table: Table
	identity_field: str
	queue_name: str

	def __init__(self, session_provider: SessionProvider, *, root: Path, interval_seconds: float = 60.0, batch_size: int = 100) -> None:
		if not isinstance(root, Path) or not root.is_absolute() or root.resolve() != root:
			raise ValueError("Требуется абсолютный канонический корень хранилища")

		if isinstance(interval_seconds, bool) or not isinstance(interval_seconds, (int, float)):
			raise ValueError("Интервал обработки должен быть числом")

		if not math.isfinite(interval_seconds) or interval_seconds <= 0:
			raise ValueError("Интервал обработки должен быть положительным и конечным")

		_require_positive_integer(batch_size, "размер порции")
		self._session_provider = session_provider
		self._root = root
		self._interval_seconds = float(interval_seconds)
		self._batch_size = batch_size
		self._after_id: UUID | None = None
		self._stop = asyncio.Event()
		self._batch_lock = asyncio.Lock()
		self._task: asyncio.Task[None] | None = None

	def start(self) -> None:
		"""Создать одну задачу; повторный запуск этого экземпляра запрещён."""
		if self._task is not None or self._stop.is_set():
			raise RuntimeError("Этот обработчик уже запускался или был закрыт")

		self._task = asyncio.create_task(self._run(), name=f"{self.queue_name}-cleanup-worker")

	def request_stop(self) -> None:
		"""Запретить новые задания, не прерывая уже выполняемое."""
		self._stop.set()

	async def wait(self) -> None:
		"""Ожидать цикл без передачи ему внешней отмены."""
		if self._task is None:
			raise RuntimeError("Обработчик ещё не запущен")

		await asyncio.shield(self._task)

	async def aclose(self) -> None:
		"""Дождаться текущего задания и остановить принадлежащую объекту задачу."""
		self.request_stop()

		if self._task is not None:
			await _wait_until_finished(self._task)

	async def _read_pending(self) -> list[UUID]:
		identity = self.job_table.c[self.identity_field]
		statement = (
			select(identity)
			.where(self.job_table.c.cleanup_complete.is_(False))
			.order_by(identity)
			.limit(self._batch_size)
		)

		if self._after_id is not None:
			statement = statement.where(identity > self._after_id)

		async with self._session_provider() as session:
			result = await session.execute(statement)
			return list(result.scalars().all())

	async def _execute_job(self, session: AsyncSession, entity_id: UUID, master_id: UUID) -> None:
		raise NotImplementedError

	async def _finish_one(self, entity_id: UUID) -> bool:
		"""Удерживать блокировку задания до завершения файлов и транзакции."""
		identity = self.job_table.c[self.identity_field]
		statement = (
			select(identity, self.job_table.c.master_id)
			.where(identity == entity_id, self.job_table.c.cleanup_complete.is_(False))
			.with_for_update(skip_locked=True)
		)

		async with self._session_provider() as session:
			try:
				row = (await session.execute(statement)).mappings().one_or_none()

				if row is None:
					return False

				await self._execute_job(session, entity_id, row["master_id"])
				await session.commit()
				return True
			except BaseException:
				await session.rollback()
				raise

	async def run_once(self) -> CleanupBatchResult:
		"""Обработать порцию с продолжением обхода после ошибочных заданий."""
		async with self._batch_lock:
			if self._stop.is_set():
				return CleanupBatchResult()

			pending = await self._read_pending()

			if not pending:
				self._after_id = None
				return CleanupBatchResult()

			completed = 0
			skipped = 0
			failed = 0

			for entity_id in pending:
				if self._stop.is_set():
					break

				self._after_id = entity_id
				outcome: list[bool] = []

				async def finish_current() -> None:
					outcome.append(await self._finish_one(entity_id))

				try:
					await _wait_until_finished(asyncio.create_task(finish_current()))

					if outcome[0]:
						completed += 1
					else:
						skipped += 1
				except Exception as error:
					failed += 1
					log.error(
						"Не удалось завершить очистку %s %s. Тип ошибки: %s",
						self.queue_name,
						entity_id,
						type(error).__name__,
					)

			return CleanupBatchResult(
				selected=len(pending),
				completed=completed,
				skipped=skipped,
				failed=failed,
			)

	async def _run(self) -> None:
		while not self._stop.is_set():
			try:
				await self.run_once()
			except Exception as error:
				log.error("Не удалось прочитать очередь %s. Тип ошибки: %s", self.queue_name, type(error).__name__)

			try:
				await asyncio.wait_for(self._stop.wait(), timeout=self._interval_seconds)
			except TimeoutError:
				pass

class CleanupWorker(_CleanupQueue):
	"""Очередь отдельных карт; имя из блока 47 сохранено."""

	job_table = MapDeletionJob.__table__
	identity_field = "map_id"
	queue_name = "maps"

	async def _execute_job(self, session: AsyncSession, entity_id: UUID, master_id: UUID) -> None:
		await management.finish_map_deletion_cleanup(session, entity_id, master_id, root=self._root)

class GameCleanupWorker(_CleanupQueue):
	"""Очередь удалённых игр с существующим предметным сервисом."""

	job_table = GameDeletionJob.__table__
	identity_field = "game_id"
	queue_name = "games"

	async def _execute_job(self, session: AsyncSession, entity_id: UUID, master_id: UUID) -> None:
		await game_deletion_service.finish_cleanup(session, entity_id, master_id, _execute_cleanup, root=self._root)

class CleanupWorkers:
	"""Совместный запуск и остановка независимых очередей игр и карт."""

	def __init__(self, session_provider: SessionProvider, *, root: Path, interval_seconds: float = 60.0, batch_size: int = 100) -> None:
		options = {"root": root, "interval_seconds": interval_seconds, "batch_size": batch_size}
		self._workers = (
			CleanupWorker(session_provider, **options),
			GameCleanupWorker(session_provider, **options),
		)
		self._started = False
		self._close_task: asyncio.Task[None] | None = None

	def start(self) -> None:
		if self._started or self._close_task is not None:
			raise RuntimeError("Этот набор обработчиков уже запускался или был закрыт")

		self._started = True

		for worker in self._workers:
			worker.start()

	async def _close_all(self) -> None:
		results = await asyncio.gather(*(worker.aclose() for worker in self._workers), return_exceptions=True)

		for result in results:
			if isinstance(result, BaseException):
				raise result

	async def aclose(self) -> None:
		"""Сначала остановить выдачу новых заданий в обеих очередях."""
		for worker in self._workers:
			worker.request_stop()

		if self._close_task is None:
			self._close_task = asyncio.create_task(self._close_all())

		await _wait_until_finished(self._close_task)