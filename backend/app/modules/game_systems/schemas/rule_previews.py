# backend/app/modules/game_systems/schemas/rule_previews.py

"""Входной контракт предпросмотра числового состояния по пользовательским правилам."""

from __future__ import annotations
from backend.app.modules.game_systems.schemas.game_rules import RulesModel, RulesProfile, SheetState


class RulesPreviewInput(RulesModel):
	"""Профиль и проверяемое состояние без сохранения и игровых действий."""

	rules: RulesProfile
	state: SheetState