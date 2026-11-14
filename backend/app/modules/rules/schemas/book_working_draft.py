# backend/app/modules/rules/schemas/book_working_draft.py

"""Чтение и сохранение общего книжного черновика формата 2."""

from backend.app.modules.rules.schemas.articles import Revision, RulesContentModel
from backend.app.modules.rules.schemas.book_draft_content import BookDraftContent
from backend.app.modules.rules.schemas.books import RuleBookDraftRead


class BookWorkingDraftUpdate(RulesContentModel):
	expected_revision: Revision
	content: BookDraftContent

class BookWorkingDraftRead(RuleBookDraftRead):
	content_json: BookDraftContent