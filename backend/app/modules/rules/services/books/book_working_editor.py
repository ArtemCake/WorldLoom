# backend/app/modules/rules/services/book_working_editor.py

"""Согласованное состояние редактора книги с собственными текстами.

Порядок блокировок совпадает с сохранением и выпуском: книга, затем черновик.
Чтение не преобразует сохранённый JSON и не увеличивает ревизию.
Недоступные внешние ссылки не препятствуют открытию собственного черновика.
"""

from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.modules.rules.models.books import RuleBookVersion
from backend.app.modules.rules.schemas.books.books import RuleBookRead, RuleBookVersionRead
from backend.app.modules.rules.schemas.books.book_working_draft import BookWorkingEditorRead
from backend.app.modules.rules.services.books import book_service
from backend.app.modules.rules.services.books.book_publication_state import book_content_changed, load_owned_snapshots


_VERSIONS = RuleBookVersion.__table__


async def get_working_editor(session: AsyncSession, book_id: UUID, actor_id: UUID) -> BookWorkingEditorRead:
	"""Открыть только собственную книгу без записи и проверки внешних зависимостей."""

	book_service._prepare(session, actor_id, book_id)

	book = await book_service._book(session, book_id, actor_id, owner_only=True, write=False)
	stored = await book_service._draft(session, book_id, write=False)
	draft = book_service._working_read(stored)

	statement = (
		select(_VERSIONS)
		.where(_VERSIONS.c.book_id == book_id)
		.order_by(_VERSIONS.c.version_number.desc())
		.limit(1)
	)
	result = await session.execute(statement)
	row = result.mappings().one_or_none()

	publication = None

	if row is not None:
		publication = book_service._read(RuleBookVersionRead, row)

	content = publication.content_json if publication is not None else None
	snapshots = await load_owned_snapshots(session, [content] if content is not None else [])
	changed = book_content_changed(book_id, draft.content_json, content, snapshots)

	return BookWorkingEditorRead(
		book=book_service._read(RuleBookRead, book),
		draft=draft,
		latest_publication=publication,
		has_unpublished_changes=changed,
	)
