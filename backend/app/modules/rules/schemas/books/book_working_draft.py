# backend/app/modules/rules/schemas/books/book_working_draft.py

"""Чтение и сохранение общего книжного черновика формата 2."""

from backend.app.modules.rules.schemas.articles import Revision, RulesContentModel
from backend.app.modules.rules.schemas.books.book_draft_content import BookDraftContent
from backend.app.modules.rules.schemas.books.books import RuleBookRead, RuleBookVersionRead, RuleBookDraftRead


class BookWorkingDraftUpdate(RulesContentModel):
	expected_revision: Revision
	content: BookDraftContent

class BookWorkingDraftRead(RuleBookDraftRead):
	content_json: BookDraftContent

class BookWorkingEditorRead(RulesContentModel):
	"""Карточка, рабочий черновик и состояние относительно последнего выпуска."""

	book: RuleBookRead
	draft: BookWorkingDraftRead
	latest_publication: RuleBookVersionRead | None = None
	has_unpublished_changes: bool