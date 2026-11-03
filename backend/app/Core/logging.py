# backend/app/core/logging.py

"""Журналирование приложения с очередью и явным жизненным циклом."""

from __future__ import annotations
import atexit
import logging
import sys
from collections.abc import Iterable
from logging.handlers import (QueueHandler, QueueListener, TimedRotatingFileHandler)
from pathlib import Path
from queue import Queue
from threading import RLock
from typing import TYPE_CHECKING
from urllib.parse import quote, quote_plus
from backend.app.core.paths import LOGS_DIR
if TYPE_CHECKING:
	from backend.app.core.settings import WebAppSettings


APP_LOGGER_NAME = "WorldLoom"

LOG_FORMAT = (
	"%(asctime)s.%(msecs)03d | %(levelname)-8s | "
	"[%(name)s:%(lineno)d] %(message)s"
)
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

MAIN_LOG_BACKUP_COUNT = 7
ERROR_LOG_BACKUP_COUNT = 30

class _SecretFormatter(logging.Formatter):
	"""Скрывает переданные секреты в сообщении и тексте исключения."""

	def __init__(self, secrets: Iterable[str]) -> None:
		super().__init__()

		variants: set[str] = set()

		for secret in secrets:
			if not secret:
				continue

			variants.update(
				(
					secret,
					quote(secret, safe=""),
					quote_plus(secret, safe=""),
				)
			)

		# Сначала заменяем более длинные совпадения.
		self._secrets = tuple(
			sorted(variants, key=len, reverse=True)
		)

	def format(self, record: logging.LogRecord) -> str:
		text = super().format(record)

		for secret in self._secrets:
			text = text.replace(secret, "[REDACTED]")

		return text

class LoggingManager:
	"""Управляет очередью и обработчиками одного процесса.

	Создание объекта не открывает файлы и не запускает поток.
	start() и stop() вызываются владельцем жизненного цикла приложения.

	Файловая ротация рассчитана на один процесс приложения,
	записывающий в указанный каталог.
	"""

	def __init__(self, log_dir: Path = LOGS_DIR) -> None:
		self._log_dir = Path(log_dir)
		self._lock = RLock()

		self._listener: QueueListener | None = None
		self._queue_handler: QueueHandler | None = None
		self._handlers: list[logging.Handler] = []

		self._previous_level = logging.NOTSET
		self._previous_propagate = True

	def start(self, *, secrets: Iterable[str] = ()) -> logging.Logger:
		"""Запустить журналирование; повторный вызов безопасен."""
		with self._lock:
			logger = logging.getLogger(APP_LOGGER_NAME)

			if self._listener is not None:
				return logger

			if logger.handlers:
				raise RuntimeError(
					"Логгер WorldLoom уже настроен другим механизмом."
				)

			secret_formatter = _SecretFormatter(secrets)
			formatter = logging.Formatter(
				fmt=LOG_FORMAT,
				datefmt=LOG_DATE_FORMAT,
			)

			self._log_dir.mkdir(parents=True, exist_ok=True)

			handlers: list[logging.Handler] = []
			queue_handler: QueueHandler | None = None
			listener: QueueListener | None = None
			listener_started = False

			previous_level = logger.level
			previous_propagate = logger.propagate

			try:
				console_handler = logging.StreamHandler(sys.stdout)
				handlers.append(console_handler)
				console_handler.setLevel(logging.DEBUG)
				console_handler.setFormatter(formatter)

				file_handler = TimedRotatingFileHandler(
					filename=self._log_dir / "worldloom.log",
					when="midnight",
					interval=1,
					backupCount=MAIN_LOG_BACKUP_COUNT,
					encoding="utf-8",
				)
				handlers.append(file_handler)
				file_handler.setLevel(logging.INFO)
				file_handler.setFormatter(formatter)

				error_handler = TimedRotatingFileHandler(
					filename=self._log_dir / "worldloom_error.log",
					when="midnight",
					interval=1,
					backupCount=ERROR_LOG_BACKUP_COUNT,
					encoding="utf-8",
				)
				handlers.append(error_handler)
				error_handler.setLevel(logging.ERROR)
				error_handler.setFormatter(formatter)

				log_queue: Queue = Queue()

				queue_handler = QueueHandler(log_queue)

				# QueueHandler форматирует сообщение и исключение
				# перед постановкой подготовленной записи в очередь.
				queue_handler.setFormatter(secret_formatter)

				listener = QueueListener(
					log_queue,
					*handlers,
					respect_handler_level=True,
				)
				listener.start()
				listener_started = True

				logger.setLevel(logging.DEBUG)
				logger.propagate = False
				logger.addHandler(queue_handler)

				# Резервная остановка при обычном завершении Python.
				atexit.register(self.stop)

			except BaseException:
				if queue_handler is not None:
					logger.removeHandler(queue_handler)

				if listener_started and listener is not None:
					listener.stop()

				if queue_handler is not None:
					queue_handler.close()

				for handler in reversed(handlers):
					handler.close()

				logger.setLevel(previous_level)
				logger.propagate = previous_propagate
				raise

			self._previous_level = previous_level
			self._previous_propagate = previous_propagate
			self._handlers = handlers
			self._queue_handler = queue_handler
			self._listener = listener

			return logger

	def stop(self) -> None:
		"""Дописать очередь и закрыть ресурсы.

		Вызывать после остановки задач, создающих записи в журнале.
		Повторный вызов ничего не делает.
		"""
		with self._lock:
			if self._listener is None:
				return

			logger = logging.getLogger(APP_LOGGER_NAME)

			listener = self._listener
			queue_handler = self._queue_handler
			handlers = self._handlers

			if queue_handler is not None:
				logger.removeHandler(queue_handler)

			try:
				# При остановленных производителях обрабатывает
				# накопленные записи до завершения потока.
				listener.stop()
			finally:
				if queue_handler is not None:
					queue_handler.close()

				try:
					for handler in reversed(handlers):
						handler.close()
				finally:
					logger.setLevel(self._previous_level)
					logger.propagate = self._previous_propagate

					self._listener = None
					self._queue_handler = None
					self._handlers = []

					atexit.unregister(self.stop)

_manager = LoggingManager()

def get_logger(module_name: str | None = None) -> logging.Logger:
	"""Получить логгер без запуска очереди и открытия файлов."""
	if not module_name:
		return logging.getLogger(APP_LOGGER_NAME)

	return logging.getLogger(
		f"{APP_LOGGER_NAME}.{module_name}"
	)

def setup_logging(settings: WebAppSettings) -> logging.Logger:
	"""Настроить журналирование с секретами из загруженных настроек."""
	secrets = (
		settings.SMTP_PASSWORD,
		settings.SMTP_FALLBACK_PASSWORD or "",
		settings.POSTGRES_PASSWORD,
		settings.SECRET_KEY,
		settings.ENCRYPTION_KEY,
		settings.EMAIL_HASH_KEY,
		settings.ADMIN_PASSWORD,
		settings.DATABASE_URL,
	)

	return _manager.start(secrets=secrets)

def shutdown_logging() -> None:
	"""Завершить журналирование приложения."""
	_manager.stop()