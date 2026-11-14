# backend/app/modules/rules/schemas/system_books.py

"""Создание книги в системе и назначение системы старой книге."""

from uuid import UUID
from backend.app.modules.rules.schemas.articles import Revision, RulesContentModel
from backend.app.modules.rules.schemas.books.books import RuleBookCreate


class SystemBookCreate(RuleBookCreate):
	"""Создание книги сразу в явно выбранной системе."""

	system_id: UUID

class BookSystemAssign(RulesContentModel):
	"""Первичное назначение системы ранее созданной книге."""

	system_id: UUID
	expected_revision: Revision

class BookSystemAssignmentRead(RulesContentModel):
	"""Результат назначения с новой ревизией черновика."""

	book_id: UUID
	system_id: UUID
	draft_revision: Revision
