# backend/app/modules/game_systems/schemas/game_system_origin.py

"""Выбор опубликованной основы и единое сохранение связанных правил."""

from typing import Any
from pydantic import Field
from backend.app.modules.catalog.schemas import GameSystemCreate
from backend.app.modules.game_systems.schemas.game_rules import RulesModel, TransportUUID
from backend.app.modules.game_systems.schemas.rule_engines import RuleEngineVersionRead


class EngineRulesSource(RulesModel):
	engine_id: TransportUUID
	engine_version_id: TransportUUID
	rules_overrides: dict[str, Any] = Field(default_factory=dict)

class GameSystemFromEngineCreate(EngineRulesSource):
	system: GameSystemCreate

class GameSystemDraftEngineSet(EngineRulesSource):
	# Обязательное поле: null означает ожидание отсутствующего черновика.
	expected_revision: int | None = Field(..., ge=1)

class GameSystemEngineEditorUpdate(GameSystemDraftEngineSet):
	system: GameSystemCreate

class GameSystemEngineOriginRead(RulesModel):
	draft_revision: int = Field(ge=1)
	engine_version: RuleEngineVersionRead