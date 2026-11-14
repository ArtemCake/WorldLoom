# backend/app/modules/rules/schemas/books/book_draft_content.py

"""Общий книжный черновик с собственными текстами и закреплёнными материалами."""

from typing import Annotated, Literal
from pydantic import Field, field_validator
from backend.app.modules.rules.schemas.books import books
from backend.app.modules.rules.schemas.articles import ArticleContent, RulesContentModel, Slug, Title


class BookTextNode(RulesContentModel):
	"""Собственный текст принадлежит общему черновику книги."""

	kind: Literal["text"] = "text"
	key: Slug
	parent_key: Slug | None = None
	position: books.Position
	title: Title | None = None
	content: ArticleContent

	@field_validator("title")
	@classmethod
	def validate_title(cls, value: str | None) -> str | None:
		if value is not None and not value.strip():
			raise ValueError("Название пункта не может состоять из пробелов")
		return value

DraftTocNode = Annotated[books.BookChapterNode | books.BookArticleNode | BookTextNode, Field(discriminator="kind")]

class BookDraftContent(books.BookContent):
	"""Формат рабочего черновика; не является форматом опубликованной книги."""

	schema_version: Literal[2] = 2
	toc: list[DraftTocNode] = Field(default_factory=list, max_length=books.MAX_TOC_NODES)

	@field_validator("schema_version", mode="before")
	@classmethod
	def validate_schema_version(cls, value):
		if type(value) is not int or value != 2:
			raise ValueError("Неподдерживаемая версия книжного черновика")
		return value

	def ensure_publishable(self) -> None:
		checked = type(self).model_validate(self.model_dump(mode="python"))
		own_texts = [node for node in checked.toc if isinstance(node, BookTextNode)]

		if not checked.article_version_ids() and not own_texts:
			raise ValueError("Для публикации книги добавьте хотя бы один текстовый раздел")

		for node in own_texts:
			node.content.ensure_publishable()

class AddBookText(RulesContentModel):
	type: Literal["add"] = "add"
	node: BookTextNode

class UpdateBookText(RulesContentModel):
	type: Literal["update"] = "update"
	key: Slug
	content: ArticleContent

class RemoveBookText(RulesContentModel):
	type: Literal["remove"] = "remove"
	key: Slug

BookTextCommand = Annotated[AddBookText | UpdateBookText | RemoveBookText, Field(discriminator="type")]
