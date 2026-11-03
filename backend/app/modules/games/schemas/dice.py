# backend/app/modules/games/schemas/dice.py

"""Входные данные броска и чтение сохранённых результатов."""

from __future__ import annotations
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class DiceRollIn(BaseModel):
	model_config = ConfigDict(extra="forbid")

	formula: str = Field(min_length=1, max_length=100)
	is_gm_hidden: bool = False
	context_type: str | None = Field(default=None, max_length=50)
	context_target_id: UUID | None = None

class DiceRollRead(BaseModel):
	model_config = ConfigDict(from_attributes=True)

	id: UUID
	session_id: UUID | None
	roller_id: UUID | None
	npc_id: UUID | None
	party_id: UUID | None
	formula: str
	result_total: int
	individual_results: list[int]
	advantage: str | None
	is_gm_hidden: bool
	context_type: str | None
	context_target_id: UUID | None
	created_at: datetime