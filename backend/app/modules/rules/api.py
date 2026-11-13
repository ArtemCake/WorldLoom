# backend/app/modules/rules/api.py

"""Сборка HTTP-маршрутов модуля правил."""

from fastapi import APIRouter
from backend.app.modules.rules.articles_api import router as articles_router
from backend.app.modules.rules.books_api import router as books_router


router = APIRouter()
router.include_router(articles_router)
router.include_router(books_router)
