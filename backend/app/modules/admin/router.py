# backend/app/modules/admin/router.py

"""Сборка административных маршрутов с раздельными правами разделов."""

from fastapi import APIRouter
from backend.app.modules.admin.api import router as rules_router
from backend.app.modules.admin.catalog_api import router as catalog_router
from backend.app.modules.admin.management_api import router as management_router
from backend.app.modules.admin.pages import router as pages_router

router = APIRouter()
router.include_router(pages_router)
router.include_router(management_router)
router.include_router(catalog_router)
router.include_router(rules_router)