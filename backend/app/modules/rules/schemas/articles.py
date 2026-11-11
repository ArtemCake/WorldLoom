# backend/app/modules/rules/schemas/articles.py

"""Контракты самостоятельных статей правил."""

from __future__ import annotations
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


Title = Annotated[str, Field(strict=True, min_length=1, max_length=200)]
Revision = Annotated[int, Field(strict=True, ge=1)]
Slug = Annotated[str, Field(strict=True, min_length=1, max_length=100, pattern=r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")]
Audience = Literal["players", "gm", "both"]
RuleKind = Literal["base", "optional", "supplement", "homebrew"]

class RulesContentModel(BaseModel):
	model_config = ConfigDict(extra="forbid", from_attributes=True)

class ArticleSource(RulesContentModel):
	"""Ссылка на источник не подтверждает право распространять его текст."""

	title: Title
	publisher: str | None = Field(default=None, strict=True, max_length=200)
	locator: str | None = Field(default=None, strict=True, max_length=500)
	url: HttpUrl | None = None
	license_name: str | None = Field(default=None, strict=True, max_length=200)
	license_url: HttpUrl | None = None
	attribution: str | None = Field(default=None, strict=True, max_length=5000)

	@field_validator("title")
	@classmethod
	def validate_title(cls, value: str) -> str:
		if not value.strip():
			raise ValueError("Название источника не может состоять из пробелов")
		return value

class ArticleContent(RulesContentModel):
	"""Полный снимок содержания; одинаковый формат для черновика и публикации."""

	schema_version: Literal[1] = 1
	title: Title
	summary: str = Field(default="", strict=True, max_length=5000)
	body: str = Field(default="", strict=True, max_length=300000)
	language: str = Field(default="ru", strict=True, min_length=2, max_length=20)
	edition_key: str | None = Field(default=None, strict=True, min_length=1, max_length=100)
	audience: Audience = "both"
	rule_kind: RuleKind = "base"
	sources: list[ArticleSource] = Field(default_factory=list, max_length=100)

	@field_validator("title", "language", "edition_key")
	@classmethod
	def validate_nonblank(cls, value: str | None) -> str | None:
		if value is not None and not value.strip():
			raise ValueError("Значение не может состоять из пробелов")
		return value

	def ensure_publishable(self) -> None:
		if not self.body.strip():
			raise ValueError("Нельзя опубликовать статью без текста")

class RuleArticleCreate(RulesContentModel):
	slug: Slug
	visibility: Literal["private", "public"] = "private"
	content: ArticleContent

class RuleArticleDraftUpdate(RulesContentModel):
	expected_revision: Revision
	content: ArticleContent

class RuleArticlePublish(RulesContentModel):
	expected_revision: Revision

class RuleArticleRead(RulesContentModel):
	id: UUID
	owner_id: UUID | None
	slug: str
	visibility: Literal["private", "public"]
	is_active: bool
	created_at: datetime
	updated_at: datetime

class RuleArticleDraftRead(RulesContentModel):
	id: UUID
	article_id: UUID
	revision: Revision
	content_json: ArticleContent
	created_at: datetime
	updated_at: datetime

class RuleArticleVersionRead(RulesContentModel):
	id: UUID
	article_id: UUID
	version_number: Revision
	source_draft_revision: Revision
	content_json: ArticleContent
	published_by: UUID | None
	published_at: datetime

class RuleArticleEditorRead(RulesContentModel):
	"""Карточка и черновик, созданные одной операцией."""

	article: RuleArticleRead
	draft: RuleArticleDraftRead

class RuleArticlePublishRead(RulesContentModel):
	"""Публикация и актуальная ревизия черновика после операции."""

	publication: RuleArticleVersionRead
	draft_revision: Revision
