# backend/app/modules/game_systems/schemas/rules/rulebook.py

from __future__ import annotations
from typing import Annotated, Literal
from pydantic import Field
from backend.app.modules.game_systems.schemas.rules.rule_calculations import CalculationModel, Code


ChapterText = Annotated[str, Field(strict=True, max_length=10000)]

class RulebookChapter(CalculationModel):
	"""Описание правил автором; не исполняемая игровая процедура."""

	label: str = Field(strict=True, min_length=1, max_length=100, pattern=r"\S")
	status: Literal["draft", "described", "unused"] = "draft"
	fields: dict[Code, ChapterText] = Field(default_factory=dict, max_length=32)
