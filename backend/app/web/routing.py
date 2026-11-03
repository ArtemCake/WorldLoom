# backend/app/web/routing.py

"""Подключение агрегаторов маршрутов без повторной регистрации вложенных роутеров."""

from fastapi import FastAPI
from backend.app.modules.admin.router import router as admin_router
from backend.app.modules.auth.api import router as auth_router
from backend.app.modules.characters.api.api import router as characters_router
from backend.app.modules.game_systems.api import router as game_systems_router
from backend.app.modules.games.api import router as games_router
from backend.app.modules.maps.api import router as maps_router
from backend.app.modules.users.api import router as users_router
from backend.app.web.pages import router as pages_router

def install_routes(app: FastAPI) -> None:
	"""Подключить подготовленные агрегаторы один раз до запуска."""
	if app.middleware_stack is not None:
		raise RuntimeError("Маршруты нужно подключать до запуска приложения")

	if getattr(app.state, "_routes_installed", False):
		raise RuntimeError("Маршруты приложения уже подключены")

	routers = (
		auth_router,
		users_router,
		admin_router,
		characters_router,
		game_systems_router,
		games_router,
		maps_router,
		pages_router,
	)

	for router in routers:
		app.include_router(router)

	app.state._routes_installed = True
