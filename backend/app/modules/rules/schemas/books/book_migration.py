# backend/app/modules/rules/schemas/books/book_migration.py

"""Контракт результата переноса текстового раздела rulebook в книгу."""

from uuid import UUID
from backend.app.modules.rules.schemas.articles import Revision, RulesContentModel


class RuleBookMigrationRead(RulesContentModel):
	"""Созданная книга и количество перенесённых узлов.

	Числовая часть профиля системы при переносе не изменяется.
	"""

	book_id: UUID
	system_id: UUID
	draft_revision: Revision
	chapters: int
	texts: int
