# backend/app/modules/game_systems/api.py

"""Сборка пользовательского каталога и перенесённых HTTP-маршрутов правил."""

from fastapi import APIRouter

from backend.app.modules.catalog.api import router as catalog_router
from backend.app.modules.game_systems.routers.calculations import router as calculations_router
from backend.app.modules.game_systems.routers.systems import router as systems_router

router = APIRouter()
router.include_router(catalog_router)
router.include_router(calculations_router)
router.include_router(systems_router)