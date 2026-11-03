# backend/app/modules/game_systems/schemas/game_system_editor.py

"""Единое создание и изменение карточки системы вместе с черновиком."""

from pydantic import Field
from backend.app.modules.catalog.schemas import GameSystemAdminRead, GameSystemCreate
from backend.app.modules.game_systems.schemas.game_rules import GameSystemRulesDraftRead, RulesModel, RulesProfile


class GameSystemEditorCreate(RulesModel):
	system: GameSystemCreate
	rules: RulesProfile

class GameSystemEditorUpdate(RulesModel):
	system: GameSystemCreate
	rules: RulesProfile

	# Обязательное поле: null означает ожидание отсутствующего черновика.
	expected_revision: int | None = Field(..., ge=1)

class GameSystemEditorRead(RulesModel):
	system: GameSystemAdminRead
	draft: GameSystemRulesDraftRead