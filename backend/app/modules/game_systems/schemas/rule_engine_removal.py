# backend/app/modules/game_systems/schemas/rule_engine_removal.py

"""Контракты плана и будущего подтверждённого выполнения операции."""

from typing import Literal
from uuid import UUID
from pydantic import Field
from backend.app.modules.game_systems.schemas.game_rules import RulesModel
from backend.app.modules.game_systems.schemas.rule_engine_lifecycle import RuleEngineRemovalPreview


class RuleEngineRemovalPlan(RuleEngineRemovalPreview):
	snapshot_token: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")

class RuleEngineRemovalExecute(RulesModel):
	snapshot_token: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
	expected_action: Literal["delete", "deactivate"]

class RuleEngineRemovalResult(RulesModel):
	engine_id: UUID
	action: Literal["deleted", "deactivated"]
	systems_count: int = Field(ge=0)
	games_count: int = Field(ge=0)
	cleanup_pending: bool