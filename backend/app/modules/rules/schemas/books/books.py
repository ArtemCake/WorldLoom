# backend/app/modules/rules/schemas/books/books.py

"""Контракты книг правил и их оглавлений."""

from __future__ import annotations
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID
from pydantic import Field, field_validator, model_validator
from backend.app.modules.rules.schemas.articles import ArticleSource, Audience, Revision, RulesContentModel, Slug, Title


Position = Annotated[int, Field(strict=True, ge=0)]
MAX_TOC_DEPTH = 32
MAX_TOC_NODES = 2000

class BookChapterNode(RulesContentModel):
	"""Глава или подраздел; текст правил хранится в статьях."""

	kind: Literal["chapter"] = "chapter"
	key: Slug
	parent_key: Slug | None = None
	position: Position
	title: Title

	@field_validator("title")
	@classmethod
	def validate_title(cls, value: str) -> str:
		if not value.strip():
			raise ValueError("Название главы не может состоять из пробелов")
		return value

class BookArticleNode(RulesContentModel):
	"""Пункт оглавления, закрепляющий конкретную публикацию статьи."""

	kind: Literal["article"] = "article"
	key: Slug
	parent_key: Slug | None = None
	position: Position
	article_version_id: UUID
	title: Title | None = None

	@field_validator("title")
	@classmethod
	def validate_title(cls, value: str | None) -> str | None:
		if value is not None and not value.strip():
			raise ValueError("Название пункта не может состоять из пробелов")
		return value

BookTocNode = Annotated[BookChapterNode | BookArticleNode, Field(discriminator="kind")]

class BookContent(RulesContentModel):
	"""Полное содержание черновика или снимка книги."""

	schema_version: Literal[1] = 1
	title: Title
	summary: str = Field(default="", strict=True, max_length=5000)
	introduction: str = Field(default="", strict=True, max_length=300000)
	language: str = Field(default="ru", strict=True, min_length=2, max_length=20)
	edition_key: str | None = Field(default=None, strict=True, min_length=1, max_length=100)
	category: Slug = "rules"
	audience: Audience = "both"
	sources: list[ArticleSource] = Field(default_factory=list, max_length=100)
	toc: list[BookTocNode] = Field(default_factory=list, max_length=MAX_TOC_NODES)

	@field_validator("schema_version", mode="before")
	@classmethod
	def validate_schema_version(cls, value):
		if type(value) is not int or value != 1:
			raise ValueError("Неподдерживаемая версия содержания книги")
		return value

	@field_validator("title", "language", "edition_key")
	@classmethod
	def validate_nonblank(cls, value: str | None) -> str | None:
		if value is not None and not value.strip():
			raise ValueError("Значение не может состоять из пробелов")
		return value

	@model_validator(mode="after")
	def validate_toc(self) -> BookContent:
		by_key = {}
		occupied_positions = set()

		for node in self.toc:
			if node.key in by_key:
				raise ValueError(f"Повторяется ключ пункта оглавления: {node.key}")

			location = (node.parent_key, node.position)

			if location in occupied_positions:
				raise ValueError("У пунктов одного уровня совпадает позиция")

			by_key[node.key] = node
			occupied_positions.add(location)

		for node in self.toc:
			if node.parent_key is None:
				continue

			parent = by_key.get(node.parent_key)

			if parent is None:
				raise ValueError(f"Не найден родитель пункта: {node.key}")

			if not isinstance(parent, BookChapterNode):
				raise ValueError("Родителем пункта может быть только глава")

		for node in self.toc:
			visited = {node.key}
			parent_key = node.parent_key
			depth = 1

			while parent_key is not None:
				if parent_key in visited:
					raise ValueError("Оглавление содержит циклическую связь")

				visited.add(parent_key)
				depth += 1

				if depth > MAX_TOC_DEPTH:
					raise ValueError("Превышена допустимая глубина оглавления")

				parent_key = by_key[parent_key].parent_key

		return self

	def article_version_ids(self) -> frozenset[UUID]:
		"""Уникальные зависимости книги без изменения порядка оглавления."""
		return frozenset(node.article_version_id for node in self.toc if isinstance(node, BookArticleNode))

	def ensure_publishable(self) -> None:
		"""Повторно проверить структуру и наличие хотя бы одной статьи."""
		checked = type(self).model_validate(self.model_dump(mode="python"))

		if not checked.article_version_ids():
			raise ValueError("Для публикации книги добавьте хотя бы одну опубликованную статью")

class RuleBookCreate(RulesContentModel):
	slug: Slug
	visibility: Literal["private", "public"] = "private"
	content: BookContent

class RuleBookDraftUpdate(RulesContentModel):
	expected_revision: Revision
	content: BookContent

class RuleBookPublish(RulesContentModel):
	expected_revision: Revision

class RuleBookRead(RulesContentModel):
	id: UUID
	owner_id: UUID | None
	slug: str
	visibility: Literal["private", "public"]
	is_active: bool
	created_at: datetime
	updated_at: datetime
	system_id: UUID | None = None

class RuleBookDraftRead(RulesContentModel):
	id: UUID
	book_id: UUID
	revision: Revision
	content_json: BookContent
	created_at: datetime
	updated_at: datetime

class RuleBookVersionRead(RulesContentModel):
	id: UUID
	book_id: UUID
	version_number: Revision
	source_draft_revision: Revision
	content_json: BookContent
	published_by: UUID | None
	published_at: datetime

class RuleBookEditorRead(RulesContentModel):
	article_unused: Literal[False] = Field(default=False, exclude=True)
	book: RuleBookRead
	draft: RuleBookDraftRead

class RuleBookPublishRead(RulesContentModel):
	publication: RuleBookVersionRead
	draft_revision: Revision
