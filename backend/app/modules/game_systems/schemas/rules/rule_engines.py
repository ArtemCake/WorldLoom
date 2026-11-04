# backend/app/modules/game_systems/schemas/rules/rule_engines.py

"""Контракты переиспользуемых основ, черновиков и публикаций."""

from __future__ import annotations
from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import Field
from backend.app.modules.game_systems.schemas.game_rules import RulesModel, RulesProfile


class RuleEngineCreate(RulesModel):
	name: str = Field(min_length=1, max_length=100, pattern=r"\S")
	slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")
	description: str | None = None
	visibility: Literal["private", "public"] = "private"
	rules_engine_version: str = Field(default="1.0", min_length=1, max_length=20, pattern=r"\S")
	rules: RulesProfile

class RuleEngineDraftUpdate(RulesModel):
	rules: RulesProfile
	expected_revision: int = Field(ge=1)

class RuleEnginePublish(RulesModel):
	expected_revision: int = Field(ge=1)

class RuleEngineRead(RulesModel):
	id: UUID
	owner_id: UUID | None
	name: str
	slug: str
	description: str | None
	visibility: Literal["private", "public"]
	is_active: bool
	created_at: datetime
	updated_at: datetime

class RuleEngineDraftRead(RulesModel):
	id: UUID
	engine_id: UUID
	rules_json: RulesProfile
	rules_engine_version: str
	revision: int = Field(ge=1)
	created_at: datetime
	updated_at: datetime

class RuleEngineVersionRead(RulesModel):
	id: UUID
	engine_id: UUID
	version_number: int = Field(ge=1)
	source_draft_revision: int = Field(ge=1)
	rules_json: RulesProfile
	rules_engine_version: str
	published_at: datetime

class RuleEngineEditorRead(RulesModel):
	engine: RuleEngineRead
	draft: RuleEngineDraftRead

class RuleEngineVersionSummary(RulesModel):
	"""Сведения о публикации без полного профиля правил."""

	id: UUID
	engine_id: UUID
	version_number: int = Field(ge=1)
	source_draft_revision: int = Field(ge=1)
	rules_engine_version: str
	published_at: datetime

class RuleEnginePage(RulesModel):
	items: list[RuleEngineRead]
	next_offset: int | None = None

class RuleEngineVersionPage(RulesModel):
	items: list[RuleEngineVersionSummary]
	next_offset: int | None = None

class RuleEngineActivityUpdate(RulesModel):
	"""Явно установить активность, проверив прочитанное состояние."""

	is_active: bool = Field(strict=True)
	expected_is_active: bool = Field(strict=True)

class RuleEngineDelete(RulesModel):
	"""Удалить неопубликованную основу с известной ревизией."""

	expected_revision: int = Field(ge=1)

class RuleEngineDeleteRead(RulesModel):
	deleted: Literal[True]
	engine_id: UUID