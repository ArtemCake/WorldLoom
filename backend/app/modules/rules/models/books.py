# backend/app/modules/rules/models/books.py

"""Карточки книг, черновики, публикации и закреплённые зависимости."""

from __future__ import annotations
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from backend.app.infrastructure.database.base import Base


UUID_TYPE = PG_UUID(as_uuid=True)

BOOK_CONTENT_CHECK = (
	"jsonb_typeof(content_json) = 'object' "
	"AND content_json @> '{\"schema_version\": 1}'::jsonb "
	"AND jsonb_typeof(content_json->'title') = 'string' "
	"AND length(btrim(content_json->>'title')) BETWEEN 1 AND 200 "
	"AND jsonb_typeof(content_json->'toc') = 'array' "
	"AND jsonb_array_length(content_json->'toc') <= 2000"
)

BOOK_DRAFT_CONTENT_CHECK = (
	"jsonb_typeof(content_json) = 'object' "
	"AND content_json->'schema_version' IN ('1'::jsonb, '2'::jsonb) "
	"AND jsonb_typeof(content_json->'title') = 'string' "
	"AND length(btrim(content_json->>'title')) BETWEEN 1 AND 200 "
	"AND jsonb_typeof(content_json->'toc') = 'array' "
	"AND jsonb_array_length(content_json->'toc') <= 2000"
)

BOOK_PUBLICATION_CHECK = "content_json @> '{\"toc\": [{\"kind\": \"article\"}]}'::jsonb"

class RuleBook(Base):
	"""Постоянная идентичность книги без изменяемого текста."""

	__tablename__ = "rule_books"
	__table_args__ = (
		UniqueConstraint("slug", name="uq_rule_books_slug"),
		CheckConstraint("slug ~ '^[a-z0-9]+([-_][a-z0-9]+)*$'", name="ck_rule_books_slug"),
		CheckConstraint("visibility IN ('private', 'public')", name="ck_rule_books_visibility"),
	)

	id: Mapped[UUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid4)
	owner_id: Mapped[UUID | None] = mapped_column(UUID_TYPE, ForeignKey("users.id", ondelete="SET NULL"), index=True)
	system_id: Mapped[UUID | None] = mapped_column(UUID_TYPE, ForeignKey("game_systems.id", name="fk_rule_books_system", ondelete="RESTRICT"),
		nullable=True, index=True)
	slug: Mapped[str] = mapped_column(String(100))
	visibility: Mapped[str] = mapped_column(String(20), server_default=text("'private'"))
	is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
	created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
	updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()"))

class RuleBookDraft(Base):
	"""Один черновик книги с контролем ревизии."""

	__tablename__ = "rule_book_drafts"
	__table_args__ = (
		UniqueConstraint("book_id", name="uq_rule_book_drafts_book"),
		CheckConstraint("revision >= 1", name="ck_rule_book_drafts_revision"),
		CheckConstraint(f"({BOOK_DRAFT_CONTENT_CHECK}) IS TRUE", name="ck_rule_book_drafts_content"),
	)

	id: Mapped[UUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid4)
	book_id: Mapped[UUID] = mapped_column(UUID_TYPE, ForeignKey("rule_books.id", ondelete="CASCADE"))
	content_json: Mapped[dict] = mapped_column(JSONB)
	revision: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
	created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
	updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()"))

	__mapper_args__ = {"version_id_col": revision}

class RuleBookVersion(Base):
	"""Неизменяемая публикация книги вместе с полным оглавлением."""

	__tablename__ = "rule_book_versions"
	__table_args__ = (
		UniqueConstraint("book_id", "version_number", name="uq_rule_book_versions_number"),
		UniqueConstraint("book_id", "source_draft_revision", name="uq_rule_book_versions_source"),
		CheckConstraint("version_number >= 1", name="ck_rule_book_versions_number"),
		CheckConstraint("source_draft_revision >= 1", name="ck_rule_book_versions_revision"),
		CheckConstraint(f"({BOOK_CONTENT_CHECK}) IS TRUE", name="ck_rule_book_versions_content"),
		CheckConstraint(BOOK_PUBLICATION_CHECK, name="ck_rule_book_versions_articles"),
	)

	id: Mapped[UUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid4)
	book_id: Mapped[UUID] = mapped_column(UUID_TYPE, ForeignKey("rule_books.id", ondelete="RESTRICT"))
	version_number: Mapped[int] = mapped_column(Integer)
	source_draft_revision: Mapped[int] = mapped_column(Integer)
	content_json: Mapped[dict] = mapped_column(JSONB)
	published_by: Mapped[UUID | None] = mapped_column(UUID_TYPE, nullable=True)
	published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

class RuleBookVersionArticle(Base):
	"""Уникальные зависимости публикации книги, формируемые PostgreSQL."""

	__tablename__ = "rule_book_version_articles"

	book_version_id: Mapped[UUID] = mapped_column(
		UUID_TYPE,
		ForeignKey("rule_book_versions.id", ondelete="RESTRICT"),
		primary_key=True,
	)
	article_version_id: Mapped[UUID] = mapped_column(
		UUID_TYPE,
		ForeignKey("rule_article_versions.id", ondelete="RESTRICT"),
		primary_key=True,
		index=True,
	)

class RuleBookText(Base):
	"""Неизменяемая принадлежность внутреннего материала книге и ключу раздела."""

	__tablename__ = "rule_book_texts"
	__table_args__ = (
		UniqueConstraint("book_id", "node_key", name="uq_rule_book_texts_key"),
		CheckConstraint("node_key ~ '^[a-z0-9]+([-_][a-z0-9]+)*$'", name="ck_rule_book_texts_key"),
	)

	article_id: Mapped[UUID] = mapped_column(UUID_TYPE, ForeignKey("rule_articles.id", ondelete="RESTRICT"), primary_key=True)
	book_id: Mapped[UUID] = mapped_column(UUID_TYPE, ForeignKey("rule_books.id", ondelete="RESTRICT"))
	node_key: Mapped[str] = mapped_column(String(100))
