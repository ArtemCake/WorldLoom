# backend/app/modules/games/api.py

"""Сборка перенесённых API-маршрутов модуля игр."""

from __future__ import annotations

from fastapi import APIRouter

from backend.app.modules.games.routers.game_state import router as game_state_router
from backend.app.modules.games.routers.lobby import router as lobby_router


router = APIRouter()
router.include_router(lobby_router)
router.include_router(game_state_router)