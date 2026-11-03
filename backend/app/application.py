# backend/app/application.py

"""Собрать приложение; подготовка БД и запуск ресурсов выполняются в lifespan."""

from __future__ import annotations
from pathlib import Path
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from backend.app.core.settings import WebAppSettings, get_settings
from backend.app.lifespan import create_lifespan
from backend.app.web.application_errors import install_exception_handlers
from backend.app.web.csrf_config import configure_csrf
from backend.app.web.middleware import install_security_middleware
from backend.app.web.rendering import create_templates
from backend.app.web.routing import install_routes
from backend.app.web.static_files import mount_static_files

def _configure_cors(app: FastAPI, settings: WebAppSettings) -> None:
	"""Разрешить запросы только с явно перечисленных источников."""
	origins = settings.BACKEND_CORS_ORIGINS

	if not origins:
		return

	if any("*" in origin for origin in origins):
		raise RuntimeError("Для CORS с cookie укажите конкретные источники без звёздочек")

	app.add_middleware(
		CORSMiddleware,
		allow_origins=origins,
		allow_credentials=True,
		allow_methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
		allow_headers=["Accept", "Content-Type", "Authorization", "X-CSRF-Token"],
		expose_headers=["X-CSRF-Token"],
	)

def _configure_sessions(app: FastAPI, settings: WebAppSettings) -> None:
	"""Сохранить сессионную cookie приложения с защитой для production."""
	app.add_middleware(
		SessionMiddleware,
		secret_key=settings.SECRET_KEY,
		session_cookie="WorldLoom_session",
		max_age=604800,
		same_site="lax",
		https_only=bool(settings.SECURE_COOKIES),
	)

def create_app(settings: WebAppSettings | None = None, *, enable_file_cleanup: bool = False) -> FastAPI:
	"""Собрать приложение; соединения и фоновые задачи создаются в lifespan."""
	current_settings = settings if settings is not None else get_settings()
	templates = create_templates(current_settings)

	configure_csrf(current_settings)

	app = FastAPI(
		title=current_settings.PROJECT_NAME,
		description=current_settings.DESCRIPTION,
		version=current_settings.VERSION,
		debug=False,
		lifespan=create_lifespan(
			current_settings,
			enable_map_cleanup=enable_file_cleanup,
			enable_game_cleanup=enable_file_cleanup,
		),
	)

	app.state.templates = templates
	app.state.project_root = Path(current_settings.BASE_DIR).resolve()

	install_exception_handlers(app)
	install_routes(app)
	mount_static_files(app)

	_configure_cors(app, current_settings)
	_configure_sessions(app, current_settings)
	install_security_middleware(app, production=current_settings.ENVIRONMENT == "production")

	return app
