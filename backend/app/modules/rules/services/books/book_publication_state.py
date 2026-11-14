# backend/app/modules/rules/services/book_publication_state.py

"""Сравнение книжного черновика с закреплённым опубликованным содержанием.

Внутренние тексты восстанавливаются только из версий выбранной публикации.
Последние версии статей не подставляются.
Модуль ничего не записывает и не проверяет доступность внешних материалов.
Вызывающий слой обязан предварительно проверить права на книгу.
"""

from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.modules.rules import errors
from backend.app.modules.rules.models.articles import RuleArticleVersion
from backend.app.modules.rules.models.books import RuleBookText
from backend.app.modules.rules.schemas.articles import ArticleContent
from backend.app.modules.rules.schemas.books.book_draft_content import BookDraftContent
from backend.app.modules.rules.schemas.books.books import BookContent
from backend.app.modules.rules.services.books.book_draft_commands import read_book_draft_content


_VERSIONS = RuleArticleVersion.__table__
_BINDINGS = RuleBookText.__table__


async def load_owned_snapshots(session: AsyncSession, contents: list[BookContent]) -> dict[UUID, dict]:
	"""Загрузить внутренние снимки для всей страницы одним запросом."""

	identifiers = set()

	for content in contents:
		identifiers.update(content.article_version_ids())

	if not identifiers:
		return {}

	source = _VERSIONS.join(_BINDINGS, _BINDINGS.c.article_id == _VERSIONS.c.article_id)
	statement = (
		select(
			_VERSIONS.c.id.label("version_id"),
			_VERSIONS.c.content_json,
			_BINDINGS.c.book_id,
			_BINDINGS.c.node_key,
		)
		.select_from(source)
		.where(_VERSIONS.c.id.in_(identifiers))
	)
	result = await session.execute(statement)

	return {row["version_id"]: dict(row) for row in result.mappings()}


def restore_publication_content(book_id: UUID, publication: BookContent, snapshots: dict[UUID, dict]) -> BookDraftContent:
	"""Представить неизменяемую публикацию в формате рабочего содержания."""

	try:
		checked = BookContent.model_validate(publication.model_dump(mode="python"))
		checked.ensure_publishable()

		payload = checked.model_dump(mode="python")
		payload["schema_version"] = 2

		for node in payload["toc"]:
			if node["kind"] != "article":
				continue

			snapshot = snapshots.get(node["article_version_id"])

			if snapshot is None:
				continue

			if snapshot["book_id"] != book_id or snapshot["node_key"] != node["key"]:
				raise ValueError("Нарушена принадлежность внутреннего текста")

			content = ArticleContent.model_validate(snapshot["content_json"])
			content.ensure_publishable()

			node.pop("article_version_id")
			node["kind"] = "text"
			node["content"] = content.model_dump(mode="python")

		return BookDraftContent.model_validate(payload)
	except (AttributeError, KeyError, TypeError, ValueError) as exc:
		raise errors.RuleBookStorageError("Не удалось восстановить содержание публикации для сравнения") from exc


def _comparable(content: BookDraftContent) -> dict:
	"""Порядок чтения задают parent_key и position, а не порядок элементов JSON."""

	payload = content.model_dump(mode="json")
	payload["toc"] = sorted(payload["toc"], key=lambda node: node["key"])

	return payload


def book_content_changed(book_id: UUID, draft, publication: BookContent | None, snapshots: dict[UUID, dict]) -> bool:
	"""Сравнить содержание, не используя номера ревизий как признак отличий."""

	try:
		checked = read_book_draft_content(draft)
	except (TypeError, ValueError) as exc:
		raise errors.RuleBookStorageError("Черновик имеет неподдерживаемый формат для сравнения") from exc

	if publication is None:
		return True

	published = restore_publication_content(book_id, publication, snapshots)

	return _comparable(checked) != _comparable(published)
