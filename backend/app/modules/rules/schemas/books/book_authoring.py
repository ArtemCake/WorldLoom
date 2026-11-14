# backend/app/modules/rules/schemas/books/book_authoring.py

"""Контракты списка собственных книг для авторского сценария."""

from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import Field
from backend.app.modules.rules.schemas.articles import Revision, RulesContentModel, Title
from backend.app.modules.rules.schemas.catalog import CatalogQuery


class AuthorBookQuery(CatalogQuery):
	"""Авторский каталог никогда не расширяется до чужих материалов."""

	scope: Literal["mine"] = "mine"
	system_id: UUID | None = None

class AuthorBookItem(RulesContentModel):
	"""Карточка черновика без его полного содержания."""

	id: UUID
	slug: str
	system_id: UUID | None
	visibility: Literal["private", "public"]
	is_active: bool

	title: Title
	summary: str = Field(strict=True, max_length=5000)
	language: str
	edition_key: str | None

	draft_revision: Revision
	draft_updated_at: datetime

	version_id: UUID | None
	version_number: Revision | None
	has_unpublished_changes: bool

class AuthorBookPage(RulesContentModel):
	items: list[AuthorBookItem]
	next_after: UUID | None = None