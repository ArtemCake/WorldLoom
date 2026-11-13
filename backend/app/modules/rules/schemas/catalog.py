# backend/app/modules/rules/schemas/catalog.py

"""Контракты каталогов опубликованных правил и чтения книг."""

from __future__ import annotations
from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import Field, field_validator
from backend.app.modules.rules.schemas.articles import Revision, RuleArticleVersionRead, RulesContentModel, Title
from backend.app.modules.rules.schemas.books import RuleBookVersionRead


class CatalogQuery(RulesContentModel):
	"""Фильтры последней публикации и продолжение списка по идентификатору."""

	scope: Literal["available", "mine"] = "available"
	limit: int = Field(default=30, strict=True, ge=1, le=100)
	after: UUID | None = None
	q: str | None = Field(default=None, strict=True, min_length=1, max_length=100)
	edition_key: str | None = Field(default=None, strict=True, min_length=1, max_length=100)
	language: str | None = Field(default=None, strict=True, min_length=2, max_length=20)

	@field_validator("q", "edition_key", "language")
	@classmethod
	def validate_nonblank(cls, value: str | None) -> str | None:
		if value is None:
			return None

		value = value.strip()

		if not value:
			raise ValueError("Фильтр не может состоять из пробелов")

		return value

class CatalogItem(RulesContentModel):
	"""Краткая карточка без черновика и полного текста публикации."""

	id: UUID
	slug: str
	visibility: Literal["private", "public"]
	is_owned: bool
	version_id: UUID
	version_number: Revision
	published_at: datetime
	title: Title
	summary: str = Field(strict=True, max_length=5000)
	edition_key: str | None
	language: str

class CatalogPage(RulesContentModel):
	items: list[CatalogItem]
	next_after: UUID | None = None

class BookReadingNode(RulesContentModel):
	"""Узел оглавления в порядке чтения с вычисленной глубиной."""

	kind: Literal["chapter", "article"]
	key: str
	parent_key: str | None
	position: int = Field(strict=True, ge=0)
	depth: int = Field(strict=True, ge=0)
	title: Title
	article_version_id: UUID | None = None

class BookReadingRead(RulesContentModel):
	"""Снимок книги, упорядоченное оглавление и уникальные снимки статей."""

	publication: RuleBookVersionRead
	toc: list[BookReadingNode]
	articles: list[RuleArticleVersionRead]