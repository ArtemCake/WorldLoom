# backend/app/modules/rules/schemas/workspace_overview.py

"""Контракт read-only обзора рабочего пространства системы (§5.1).

Собирает паспорт системы, черновик правил, основу и книги
без модификации данных и без новых путей записи.
"""

from __future__ import annotations
from datetime import datetime
from uuid import UUID
from pydantic import Field
from backend.app.modules.rules.schemas.articles import Revision, RulesContentModel


class WorkspaceSystemPassport(RulesContentModel):
	"""Паспорт игровой системы."""

	id: UUID
	name: str
	slug: str
	description: str | None = None
	is_active: bool
	rules_engine_version: str
	current_rules_version_id: UUID | None = None
	created_at: datetime
	updated_at: datetime


class WorkspaceRulesDraft(RulesContentModel):
	"""Черновик правил системы (пустой профиль допустим, §4.1)."""

	id: UUID
	system_id: UUID
	revision: Revision
	rules_json: dict
	created_at: datetime
	updated_at: datetime


class WorkspaceEngineOrigin(RulesContentModel):
	"""Основа правил черновика и его переопределения."""

	engine_version_id: UUID
	rules_overrides_json: dict


class WorkspaceRulesOverview(RulesContentModel):
	"""Состояние черновика правил и его основы."""

	draft: WorkspaceRulesDraft | None = None
	engine: WorkspaceEngineOrigin | None = None


class WorkspaceBookSummary(RulesContentModel):
	"""Книга системы с последней публикацией (если есть)."""

	book_id: UUID
	slug: str
	title: str
	latest_version: int | None = None
	latest_published_at: datetime | None = None
	version_id: UUID | None = None
	content_json: dict | None = None
	is_published: bool = False


class WorkspaceOverview(RulesContentModel):
	"""Read-only обзор рабочего пространства системы (§5.1).

	Флаги выводятся из данных и показывают незавершённость (§4.1):
	- rules_draft_present: черновик правил существует;
	- rules_published: у системы есть опубликованный комплект;
	- books_published: число книг с хотя бы одной публикацией.

	При публикации правил добавляется published_rules_version_id —
	идентификатор версии, которая фиксирует текущий комплект системы.
	"""

	system: WorkspaceSystemPassport
	rules: WorkspaceRulesOverview
	books: list[WorkspaceBookSummary] = Field(default_factory=list)
	rules_draft_present: bool = False
	rules_published: bool = False
	books_published: int = 0
	published_rules_version_id: UUID | None = None
