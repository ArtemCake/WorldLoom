# backend/app/modules/game_systems/routers/calculations.py

"""Административный HTTP-предпросмотр пользовательских числовых правил."""

from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Response
from backend.app.modules.admin.dependencies import require_content_manager
from backend.app.modules.game_systems.rules.attribute_engine import evaluate_attributes
from backend.app.modules.game_systems.rules.rules_engine import evaluate_sheet_state
from backend.app.modules.game_systems.schemas.rules.rule_calculations import AttributePreviewInput, AttributePreviewResult
from backend.app.modules.game_systems.schemas.rules.rule_previews import RulesPreviewInput
from backend.app.web.csrf import enforce_csrf


ACCESS_DEPENDENCIES = [Depends(require_content_manager), Depends(enforce_csrf)]
router = APIRouter(prefix="/admin/game-systems/rules", tags=["game-system-calculations"], dependencies=ACCESS_DEPENDENCIES)

@router.post("/attributes/preview", response_model=AttributePreviewResult, operation_id="adminPreviewGameSystemAttributes")
def preview_attributes(data: AttributePreviewInput, response: Response) -> AttributePreviewResult:
	response.headers["Cache-Control"] = "no-store"

	try:
		return evaluate_attributes(data)
	except ValueError as error:
		raise HTTPException(status_code=422, detail=str(error), headers={"Cache-Control": "no-store"}) from error

@router.post("/preview", response_model=AttributePreviewResult, operation_id="adminPreviewGameRules")
def preview_rules(data: RulesPreviewInput, response: Response) -> AttributePreviewResult:
	response.headers["Cache-Control"] = "no-store"

	try:
		return evaluate_sheet_state(data.rules, data.state)
	except ValueError as error:
		raise HTTPException(status_code=422, detail=str(error), headers={"Cache-Control": "no-store"}) from error