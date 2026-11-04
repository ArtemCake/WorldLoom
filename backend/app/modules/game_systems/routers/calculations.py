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
from backend.app.modules.game_systems.rules.resource_validation import initial_resource_values, resolve_resource_maxima
from backend.app.modules.game_systems.schemas.rules.rule_calculations import CalculationValue, Code
from backend.app.modules.game_systems.schemas.rules.rule_resources import ResourceDefinitions


ACCESS_DEPENDENCIES = [Depends(require_content_manager), Depends(enforce_csrf)]
router = APIRouter(prefix="/admin/game-systems/rules", tags=["game-system-calculations"], dependencies=ACCESS_DEPENDENCIES)

class ResourcePreviewResult(AttributePreviewResult):
	"""Числовой расчёт и начальное заполнение ресурсов для переданного состояния."""

	resource_limits: dict[Code, CalculationValue]
	resource_initial: dict[Code, CalculationValue]

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

@router.post("/resources/preview", response_model=ResourcePreviewResult, operation_id="adminPreviewGameRuleResources")
def preview_resource_rules(data: RulesPreviewInput, response: Response) -> ResourcePreviewResult:
	response.headers["Cache-Control"] = "no-store"

	try:
		result = evaluate_sheet_state(data.rules, data.state)
		definitions = ResourceDefinitions(resources=data.rules.resources)
		limits = resolve_resource_maxima(definitions, result)
		initial = initial_resource_values(definitions, limits)

		payload = result.model_dump()
		payload.update(resource_limits=limits, resource_initial=initial)

		return ResourcePreviewResult.model_validate(payload)
	except ValueError as error:
		raise HTTPException(status_code=422, detail=str(error), headers={"Cache-Control": "no-store"}) from error