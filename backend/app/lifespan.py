# backend/app/lifespan.py

"""Жизненный цикл приложения с подготовкой БД и освобождением ресурсов."""

from __future__ import annotations
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from backend.commands.create_initial_admin import create_initial_admin
from backend.commands.migrate import apply_migrations
from backend.app.bootstrap import build_resources
from backend.app.core.logging import get_logger, setup_logging, shutdown_logging
from backend.app.core.settings import WebAppSettings, get_settings
from backend.app.modules.games.services.cleanup_worker import CleanupWorkers
from backend.app.core.map_storage import get_map_images_root


log = get_logger(__name__)
LifespanHandler = Callable[[FastAPI], AbstractAsyncContextManager[None]]

def _get_cleanup_root(settings: WebAppSettings) -> Path:
	"""Использовать тот же корень, что и HTTP-операции с картами."""
	return get_map_images_root(settings)


async def _prepare_database(settings: WebAppSettings) -> None:
	"""Применить существующие миграции и подготовить первого администратора."""
	log.info("Начато применение существующих миграций.")

	try:
		await apply_migrations(settings)
	except Exception as error:
		log.error("Применение миграций не завершено. Тип ошибки: %s", type(error).__name__)
		raise

	log.info("Применение миграций завершено.")
	log.info("Начата проверка первого администратора.")

	try:
		result = await create_initial_admin(settings)
	except Exception as error:
		log.error("Подготовка администратора не завершена. Тип ошибки: %s", type(error).__name__)
		raise

	messages = {
		"exists": "Администратор уже существует. Изменения не выполнялись.",
		"promoted": "Существующему аккаунту назначены административные права. Пароль сохранён.",
		"created": "Первый администратор создан. Смените пароль после первого входа.",
	}
	log.info("%s", messages[result])

def create_lifespan(settings: WebAppSettings | None = None, *, enable_map_cleanup: bool = False, enable_game_cleanup: bool = False) -> LifespanHandler:
	"""Подготовить БД, запустить ресурсы и включённые фоновые операции."""

	@asynccontextmanager
	async def lifespan(app: FastAPI) -> AsyncIterator[None]:
		state_names = ("resources", "settings", "database")

		if any(hasattr(app.state, name) for name in state_names):
			raise RuntimeError("Ресурсы приложения или их зависимости уже установлены")

		if enable_map_cleanup != enable_game_cleanup:
			raise RuntimeError("Общий обработчик требует совместного включения очистки игр и карт")

		current_settings = settings if settings is not None else get_settings()

		async with AsyncExitStack() as stack:
			setup_logging(current_settings)
			stack.callback(shutdown_logging)

			cleanup_root = _get_cleanup_root(current_settings) if enable_map_cleanup else None

			if cleanup_root is None:
				log.warning("Фоновая очистка файлов игр и карт выключена.")

			await _prepare_database(current_settings)

			try:
				resources = build_resources(current_settings)
				stack.push_async_callback(resources.database.dispose)
				await resources.database.check_connection()
			except BaseException as error:
				log.error("Не удалось подготовить инфраструктуру. Тип ошибки: %s", type(error).__name__)
				raise

			values = {
				"resources": resources,
				"settings": resources.settings,
				"database": resources.database,
			}

			for name, value in values.items():
				setattr(app.state, name, value)
				stack.callback(delattr, app.state, name)

			if cleanup_root is not None:
				workers = CleanupWorkers(resources.database.session, root=cleanup_root)
				stack.push_async_callback(workers.aclose)
				workers.start()
				log.info("Запущена фоновая очистка файлов игр и карт.")

			log.info("Инфраструктура приложения готова.")

			try:
				yield
			finally:
				log.info("Начато освобождение ресурсов приложения.")

	return lifespan