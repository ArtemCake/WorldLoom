# backend/app/modules/rules/services/book_reader_service.py

"""Чтение опубликованной книги с закреплёнными снимками статей.

Проверку доступа и блокировки выполняет сервис книги.
Статьи загружаются одним запросом, без запроса на каждый пункт оглавления.
Markdown возвращается как данные, а не исполняется.
"""

from __future__ import annotations
from collections import defaultdict
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.modules.rules import errors
from backend.app.modules.rules.models.articles import RuleArticleVersion
from backend.app.modules.rules.schemas.articles import RuleArticleVersionRead
from backend.app.modules.rules.schemas.books import BookArticleNode, RuleBookVersionRead
from backend.app.modules.rules.schemas.catalog import BookReadingNode, BookReadingRead
from backend.app.modules.rules.services import book_service


_VERSIONS = RuleArticleVersion.__table__

def _assemble(publication: RuleBookVersionRead, articles: list[RuleArticleVersionRead]) -> BookReadingRead:
	"""Построить порядок чтения, не изменяя сохранённое оглавление."""
	try:
		publication = RuleBookVersionRead.model_validate(publication.model_dump(mode="python"))
		articles = [RuleArticleVersionRead.model_validate(item.model_dump(mode="python")) for item in articles]
	except ValueError as exc:
		raise errors.RuleBookStorageError("Сохранённые данные книги или статей имеют неподдерживаемый формат") from exc

	expected = publication.content_json.article_version_ids()
	by_id = {article.id: article for article in articles}

	if len(by_id) != len(articles) or set(by_id) != set(expected):
		raise errors.RuleBookStorageError("Состав статей не соответствует опубликованному оглавлению")

	children = defaultdict(list)

	for node in publication.content_json.toc:
		children[node.parent_key].append(node)

	for siblings in children.values():
		siblings.sort(key=lambda node: node.position)

	toc = []
	ordered_articles = []
	included = set()
	stack = [(node, 0) for node in reversed(children[None])]

	while stack:
		node, depth = stack.pop()
		article_id = None
		title = node.title

		if isinstance(node, BookArticleNode):
			article_id = node.article_version_id
			article = by_id[article_id]
			title = title if title is not None else article.content_json.title

			if article_id not in included:
				included.add(article_id)
				ordered_articles.append(article)

		values = {
			"kind": node.kind,
			"key": node.key,
			"parent_key": node.parent_key,
			"position": node.position,
			"depth": depth,
			"title": title,
			"article_version_id": article_id,
		}
		toc.append(BookReadingNode(**values))
		stack.extend((child, depth + 1) for child in reversed(children[node.key]))

	if len(toc) != len(publication.content_json.toc):
		raise errors.RuleBookStorageError("Не удалось построить полное оглавление книги")

	return BookReadingRead(publication=publication, toc=toc, articles=ordered_articles)

async def read_book(session: AsyncSession, book_id: UUID, version_id: UUID, actor_id: UUID) -> BookReadingRead:
	publication = await book_service.get_book_version(session, book_id, version_id, actor_id)
	identifiers = publication.content_json.article_version_ids()

	statement = select(_VERSIONS).where(_VERSIONS.c.id.in_(identifiers))
	result = await session.execute(statement)

	try:
		articles = [RuleArticleVersionRead.model_validate(dict(row)) for row in result.mappings()]
	except ValueError as exc:
		raise errors.RuleBookStorageError("Закреплённая статья имеет неподдерживаемый формат") from exc

	return _assemble(publication, articles)
