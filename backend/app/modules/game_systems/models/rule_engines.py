# backend/app/modules/game_systems/models/rule_engines.py

"""ORM-модели переиспользуемых движков, черновиков и публикаций."""

from __future__ import annotations
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import (Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, inspect, text)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from backend.app.infrastructure.database.base import Base


def _identity_repr(instance: object, *, label: str) -> str:
	"""Представление без загрузки атрибутов и содержимого правил."""
	state = inspect(instance)
	identifier = (
		state.identity[0]
		if state.identity is not None
		else state.dict.get("id")
	)
	return f"<{label}(id={identifier!r})>"

class RuleEngine(Base):
	"""Карточка движка; правила хранятся в черновике и публикациях."""

	__tablename__ = "rule_engines"
	__table_args__ = (
		UniqueConstraint("slug", name="uq_rule_engines_slug"),
		CheckConstraint(
			"visibility IN ('private', 'public')",
			name="ck_rule_engines_visibility",
		),
	)

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		primary_key=True,
		default=uuid4,
	)
	owner_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("users.id", ondelete="SET NULL"),
		nullable=True,
		index=True,
	)
	name: Mapped[str] = mapped_column(String(100), nullable=False)
	slug: Mapped[str] = mapped_column(String(100), nullable=False)
	description: Mapped[str | None] = mapped_column(Text, nullable=True)
	visibility: Mapped[str] = mapped_column(
		String(20),
		nullable=False,
		server_default=text("'private'"),
	)
	is_active: Mapped[bool] = mapped_column(
		Boolean,
		nullable=False,
		server_default=text("true"),
	)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		nullable=False,
		server_default=text("now()"),
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		nullable=False,
		server_default=text("now()"),
		onupdate=text("now()"),
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="RuleEngine")

class RuleEngineDraft(Base):
	"""Один редактируемый черновик на движок."""

	__tablename__ = "rule_engine_drafts"
	__table_args__ = (
		UniqueConstraint(
			"engine_id",
			name="uq_rule_engine_drafts_engine",
		),
		CheckConstraint(
			"revision >= 1",
			name="ck_rule_engine_drafts_revision",
		),
		CheckConstraint(
			"jsonb_typeof(rules_json) = 'object'",
			name="ck_rule_engine_drafts_rules_object",
		),
	)

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		primary_key=True,
		default=uuid4,
	)
	engine_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("rule_engines.id", ondelete="CASCADE"),
		nullable=False,
	)
	rules_json: Mapped[dict] = mapped_column(JSONB, nullable=False)

	# Версия программного исполнителя, а не номер публикации.
	rules_engine_version: Mapped[str] = mapped_column(
		String(20),
		nullable=False,
	)
	revision: Mapped[int] = mapped_column(
		Integer,
		nullable=False,
		default=1,
		server_default=text("1"),
	)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		nullable=False,
		server_default=text("now()"),
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		nullable=False,
		server_default=text("now()"),
		onupdate=text("now()"),
	)

	__mapper_args__ = {"version_id_col": revision}

	def __repr__(self) -> str:
		return _identity_repr(self, label="RuleEngineDraft")

class RuleEngineVersion(Base):
	"""Опубликованный снимок правил движка.

	Запрет изменения публикаций не реализуется самим ORM-описанием.
	"""

	__tablename__ = "rule_engine_versions"
	__table_args__ = (
		UniqueConstraint(
			"engine_id",
			"version_number",
			name="uq_rule_engine_versions_number",
		),
		CheckConstraint(
			"version_number >= 1",
			name="ck_rule_engine_versions_number",
		),
		CheckConstraint(
			"source_draft_revision >= 1",
			name="ck_rule_engine_versions_source_revision",
		),
		CheckConstraint(
			"jsonb_typeof(rules_json) = 'object'",
			name="ck_rule_engine_versions_rules_object",
		),
	)

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		primary_key=True,
		default=uuid4,
	)
	engine_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("rule_engines.id", ondelete="RESTRICT"),
		nullable=False,
	)
	version_number: Mapped[int] = mapped_column(
		Integer,
		nullable=False,
	)
	source_draft_revision: Mapped[int] = mapped_column(
		Integer,
		nullable=False,
	)
	rules_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
	rules_engine_version: Mapped[str] = mapped_column(
		String(20),
		nullable=False,
	)
	published_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		nullable=False,
		server_default=text("now()"),
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="RuleEngineVersion")