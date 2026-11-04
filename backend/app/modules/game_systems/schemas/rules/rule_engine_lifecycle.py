# backend/app/modules/game_systems/schemas/rules/rule_engine_lifecycle.py

"""Контракт предварительного анализа известных зависимостей основы.

Предлагаемое действие не является разрешением на удаление.
Полный план удаления и его повторная проверка выполняются отдельно.
"""

from typing import Literal
from uuid import UUID
from pydantic import Field
from backend.app.modules.game_systems.schemas.game_rules import RulesModel


class RuleEngineRemovalPreview(RulesModel):
	engine_id: UUID
	engine_name: str

	versions_count: int = Field(ge=0)
	systems_count: int = Field(ge=0)
	games_count: int = Field(ge=0)
	sessions_count: int = Field(ge=0)
	unowned_games_count: int = Field(ge=0)

	proposed_action: Literal["delete", "deactivate", "blocked"]