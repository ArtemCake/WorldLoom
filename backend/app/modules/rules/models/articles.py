# backend/app/modules/rules/models/articles.py

"""ORM-модели статей, черновиков и опубликованных снимков."""

from __future__ import annotations
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from backend.app.infrastructure.database.base import Base


UUID_TYPE = PG_UUID(as_uuid=True)

CONTENT_CHECK = (
	"jsonb_typeof(content_json) = 'object' "
	"AND content_json @> '{\"schema_version\": 1}'::jsonb "
	"AND jsonb_typeof(content_json->'title') = 'string' "
	"AND length(btrim(content_json->>'title')) BETWEEN 1 AND 200 "
	"AND jsonb_typeof(content_json->'body') = 'string' "
	"AND length(content_json->>'body') <= 300000"
)

class RuleArticle(Base):
	"""Постоянная идентичность; текст находится в черновике и публикациях."""

	__tablename__ = "rule_articles"
	__table_args__ = (
		UniqueConstraint("slug", name="uq_rule_articles_slug"),
		CheckConstraint("slug ~ '^[a-z0-9]+([-_][a-z0-9]+)*$'", name="ck_rule_articles_slug"),
		CheckConstraint("visibility IN ('private', 'public')", name="ck_rule_articles_visibility"),
	)

	id: Mapped[UUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid4)
	owner_id: Mapped[UUID | None] = mapped_column(UUID_TYPE, ForeignKey("users.id", ondelete="SET NULL"), index=True)
	slug: Mapped[str] = mapped_column(String(100))
	visibility: Mapped[str] = mapped_column(String(20), server_default=text("'private'"))
	is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
	created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
	updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()"))

class RuleArticleDraft(Base):
	"""Один черновик статьи с оптимистической проверкой ревизии."""

	__tablename__ = "rule_article_drafts"
	__table_args__ = (
		UniqueConstraint("article_id", name="uq_rule_article_drafts_article"),
		CheckConstraint("revision >= 1", name="ck_rule_article_drafts_revision"),
		CheckConstraint(f"({CONTENT_CHECK}) IS TRUE", name="ck_rule_article_drafts_content"),
	)

	id: Mapped[UUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid4)
	article_id: Mapped[UUID] = mapped_column(UUID_TYPE, ForeignKey("rule_articles.id", ondelete="CASCADE"))
	content_json: Mapped[dict] = mapped_column(JSONB)
	revision: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
	created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
	updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()"))

	__mapper_args__ = {"version_id_col": revision}

class RuleArticleVersion(Base):
	"""Опубликованный снимок; изменение блокирует PostgreSQL-триггер."""

	__tablename__ = "rule_article_versions"
	__table_args__ = (
		UniqueConstraint("article_id", "version_number", name="uq_rule_article_versions_number"),
		UniqueConstraint("article_id", "source_draft_revision", name="uq_rule_article_versions_source"),
		CheckConstraint("version_number >= 1", name="ck_rule_article_versions_number"),
		CheckConstraint("source_draft_revision >= 1", name="ck_rule_article_versions_revision"),
		CheckConstraint(f"({CONTENT_CHECK}) IS TRUE", name="ck_rule_article_versions_content"),
		CheckConstraint("length(btrim(content_json->>'body')) > 0", name="ck_rule_article_versions_body"),
	)

	id: Mapped[UUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid4)
	article_id: Mapped[UUID] = mapped_column(UUID_TYPE, ForeignKey("rule_articles.id", ondelete="RESTRICT"))
	version_number: Mapped[int] = mapped_column(Integer)
	source_draft_revision: Mapped[int] = mapped_column(Integer)
	content_json: Mapped[dict] = mapped_column(JSONB)
	published_by: Mapped[UUID | None] = mapped_column(UUID_TYPE, nullable=True)
	published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))