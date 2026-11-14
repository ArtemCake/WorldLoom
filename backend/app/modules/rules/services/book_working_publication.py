# backend/app/modules/rules/services/book_working_publication.py

"""Атомарный выпуск общего книжного черновика и его внутренних текстов.

Транзакцией управляет вызывающий слой.
После любой ошибки требуется откат всей операции.
Внутренние материалы записываются только после блокировки книги и черновика.
"""

from uuid import UUID, uuid4
from sqlalchemy import func, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.modules.rules import errors
from backend.app.modules.rules.models.articles import RuleArticle, RuleArticleVersion
from backend.app.modules.rules.models.books import RuleBookText, RuleBookVersion
from backend.app.modules.rules.schemas.articles import RuleArticleVersionRead
from backend.app.modules.rules.schemas.books import RuleBookPublish, RuleBookPublishRead, RuleBookVersionRead
from backend.app.modules.rules.services import book_service
from backend.app.modules.rules.services.book_draft_publication import collect_owned_texts, compile_book_publication


_ARTICLES = RuleArticle.__table__
_ARTICLE_VERSIONS = RuleArticleVersion.__table__
_BINDINGS = RuleBookText.__table__
_BOOK_VERSIONS = RuleBookVersion.__table__

BookPublish = RuleBookPublish
PublishRead = RuleBookPublishRead
VersionRead = RuleBookVersionRead
TextVersionRead = RuleArticleVersionRead


async def _new_binding(session: AsyncSession, book_id: UUID, key: str) -> UUID:
	"""Создать техническую карточку и сразу закрепить её за книгой."""

	article_id = uuid4()
	statement = (
		pg_insert(_ARTICLES)
		.values(
			id=article_id,
			owner_id=None,
			slug=f"booktext-{article_id.hex}",
			visibility="private",
			is_active=True,
		)
		.on_conflict_do_nothing()
		.returning(_ARTICLES.c.id)
	)
	result = await session.execute(statement)

	if result.scalar_one_or_none() is None:
		raise errors.RuleBookConflict("Не удалось выделить идентичность внутреннего текста")

	statement = insert(_BINDINGS).values(article_id=article_id, book_id=book_id, node_key=key)
	await session.execute(statement)

	return article_id


async def _materialize(session: AsyncSession, book_id: UUID, actor_id: UUID, draft) -> dict[str, TextVersionRead]:
	"""Записать снимки собственных текстов под блокировкой всей книги."""

	texts = collect_owned_texts(draft.content_json)
	statement = select(_BINDINGS).where(_BINDINGS.c.book_id == book_id)
	result = await session.execute(statement)
	identities = {row["node_key"]: row["article_id"] for row in result.mappings()}
	publications = {}

	for key in sorted(texts):
		article_id = identities.get(key)

		if article_id is None:
			article_id = await _new_binding(session, book_id, key)

		statement = (
			select(func.coalesce(func.max(_ARTICLE_VERSIONS.c.version_number), 0) + 1)
			.where(_ARTICLE_VERSIONS.c.article_id == article_id)
		)
		result = await session.execute(statement)
		number = result.scalar_one()

		statement = (
			insert(_ARTICLE_VERSIONS)
			.values(
				article_id=article_id,
				version_number=number,
				source_draft_revision=draft.revision,
				content_json=texts[key].model_dump(mode="json"),
				published_by=actor_id,
			)
			.returning(*_ARTICLE_VERSIONS.c)
		)
		result = await session.execute(statement)
		publications[key] = book_service._read(TextVersionRead, result.mappings().one())

	return publications


async def publish_working_book(session: AsyncSession, book_id: UUID, actor_id: UUID, data: BookPublish) -> PublishRead:
	"""Выпустить сохранённую книгу и все собственные тексты одной транзакцией."""

	book_service._prepare(session, actor_id, book_id)
	data = book_service._request(BookPublish, data)

	book = await book_service._book(session, book_id, actor_id, owner_only=True, write=True)

	if not book["is_active"]:
		raise errors.RuleBookConflict("Перед публикацией активируйте книгу")

	stored = await book_service._draft(session, book_id, write=True)
	book_service._check_revision(stored, data.expected_revision)
	draft = book_service._working_read(stored)

	try:
		draft.content_json.ensure_publishable()
	except ValueError as exc:
		raise errors.RuleBookConflict("Для публикации заполните собственные тексты и проверьте оглавление") from exc

	await book_service._dependencies(
		session,
		draft.content_json,
		actor_id,
		public_only=book["visibility"] == "public",
	)

	texts = await _materialize(session, book_id, actor_id, draft)

	try:
		content = compile_book_publication(draft.content_json, texts)
	except (TypeError, ValueError) as exc:
		raise errors.RuleBookStorageError("Не удалось согласовать книгу со снимками собственных текстов") from exc

	await book_service._dependencies(
		session,
		content,
		actor_id,
		public_only=book["visibility"] == "public",
		book_id=book_id,
	)

	statement = (
		select(func.coalesce(func.max(_BOOK_VERSIONS.c.version_number), 0) + 1)
		.where(_BOOK_VERSIONS.c.book_id == book_id)
	)
	result = await session.execute(statement)
	number = result.scalar_one()

	statement = (
		insert(_BOOK_VERSIONS)
		.values(
			book_id=book_id,
			version_number=number,
			source_draft_revision=draft.revision,
			content_json=content.model_dump(mode="json"),
			published_by=actor_id,
		)
		.returning(*_BOOK_VERSIONS.c)
	)
	result = await session.execute(statement)
	publication = book_service._read(VersionRead, result.mappings().one())

	saved = await book_service._save_draft(session, stored, working=True)
	await book_service._touch_book(session, book_id)

	return PublishRead(publication=publication, draft_revision=saved.revision)