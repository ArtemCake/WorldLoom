# backend/app/modules/rules/services/books/rulebook_service.py

"""Перенос текстового раздела rulebook системы в отдельную книгу.

Числовая часть профиля системы (calculations, initial_attributes,
resources) не изменяется. Раздел rulebook остаётся в черновике до
окончательного переключения потребителей; этот сервис только
создаёт книгу и заполняет её перенесённым содержанием.

Транзакцией управляет вызывающий слой. Разрешение автора системы
проверяет вызывающий слой.
"""

from __future__ import annotations
import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.modules.rules import errors
from backend.app.modules.rules.models.books import RuleBook, RuleBookDraft
from backend.app.modules.rules.schemas.books.book_migration import RuleBookMigrationRead
from backend.app.modules.rules.schemas.books.book_working_draft import (
    BookWorkingDraftUpdate,
)
from backend.app.modules.rules.schemas.books.books import (
    BookContent,
    RuleBookCreate,
)
from backend.app.modules.rules.schemas.system_books import SystemBookCreate
from backend.app.modules.rules.services import system_books
from backend.app.modules.rules.services.books import book_service
from backend.app.modules.rules.services.books.rulebook_migration import (
    rulebook_to_book_draft,
)

_BOOKS = RuleBook.__table__
_DRAFTS = RuleBookDraft.__table__


def _normalize_system_slug(system_id: UUID) -> str:
	"""Устойчивый код книги на основе идентификатора системы."""
	return f"system-rules-{system_id.hex[:12]}"

def _system_book_slug(rules_json: dict, system_id: UUID) -> str:
	"""Собрать допустимый slug книги из правил системы."""
	raw = str(rules_json.get("slug") or "").strip().lower()
	raw = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")

	if raw:
		return f"{raw}-rules"[:100]

	return _normalize_system_slug(system_id)

def _rulebook(rules_json: dict) -> dict:
	rulebook = rules_json.get("rulebook")

	if rulebook is None:
		return {}

	if not isinstance(rulebook, dict):
		raise errors.InvalidRuleBook("Раздел rulebook имеет неподдерживаемый формат")

	return rulebook

def _node_kind(node) -> str:
	"""Вид узла оглавления для модели контракта или словаря из БД."""
	if isinstance(node, dict):
		return str(node.get("kind"))

	if hasattr(node, "kind"):
		return str(node.kind)

	return ""

def _migration_read(book_id: UUID, system_id: UUID, revision: int, nodes) -> RuleBookMigrationRead:
	"""Собрать результат переноса по узлам оглавления черновика."""
	chapters = 0
	texts = 0

	for node in nodes:
		kind = _node_kind(node)
		if kind == "chapter":
			chapters += 1
		elif kind == "text":
			texts += 1

	return RuleBookMigrationRead(
		book_id=book_id,
		system_id=system_id,
		draft_revision=revision,
		chapters=chapters,
		texts=texts,
	)

async def migrate_system_rulebook(
	session: AsyncSession,
	*,
	system_id: UUID,
	actor_id: UUID,
	rules_json: dict,
	title: str,
	summary: str = "",
	language: str = "ru",
	edition_key: str | None = None,
) -> RuleBookMigrationRead:
	"""Создать книгу системы и перенести в неё тексты rulebook.

	Вызывающий слой обязан заблокировать черновик системы и
	проверить право автора до обращения к этому сервису.
	"""

	if not isinstance(rules_json, dict):
		raise errors.InvalidRuleBook("Черновик правил должен быть словарём")

	rulebook = _rulebook(rules_json)
	draft = rulebook_to_book_draft(
		rulebook,
		title=title,
		summary=summary,
		language=language,
		edition_key=edition_key,
	)

	slug = _system_book_slug(rules_json, system_id)

	# Идемпотентность (§26.3): миграция обязана распознавать уже
	# перенесённые записи и не создавать дубликатов при повторе или
	# после частичного сбоя.
	existing = (
		await session.execute(
			select(_BOOKS.c.id)
			.where(
				(_BOOKS.c.slug == slug)
				& (_BOOKS.c.system_id == system_id)
				& (_BOOKS.c.is_active.is_(True))
			)
		)
	).scalar_one_or_none()

	if existing is not None:
		draft_row = (
			await session.execute(
				select(_DRAFTS.c.revision, _DRAFTS.c.content_json)
				.where(_DRAFTS.c.book_id == existing)
				.with_for_update()
			)
		).mappings().one_or_none()

		if draft_row is None:
			raise errors.RuleBookStorageError(
				"У перенесённой книги отсутствует обязательный черновик"
			)

		# revision == 1 означает незавершённый перенос: книга создана,
		# но перенесённое содержание ещё не записано (create_system_book
		# даёт пустое оглавление). Дозаполняем черновик.
		if draft_row["revision"] == 1:
			saved = await book_service.update_working_draft(
				session,
				existing,
				actor_id,
				BookWorkingDraftUpdate(expected_revision=1, content=draft),
			)

			return _migration_read(
				existing, system_id, saved.revision, saved.content_json.toc
			)

		# Перенос уже завершён ранее. Черновик не перезаписывается,
		# чтобы не затереть правки автора; возвращается фактическое
		# состояние книги.
		return _migration_read(
			existing,
			system_id,
			draft_row["revision"],
			draft_row["content_json"].get("toc", []),
		)

	# Книга создаётся с пустым оглавлением прежнего формата,
	# затем заполняется перенесённым содержанием формата 2.
	created = await system_books.create_system_book(
		session,
		actor_id,
		SystemBookCreate(
			slug=slug,
			visibility="private",
			system_id=system_id,
			content=BookContent(
				title=draft.title,
				summary=draft.summary,
				language=draft.language,
				edition_key=draft.edition_key,
				toc=[],
			),
		),
	)

	saved = await book_service.update_working_draft(
		session,
		created.book.id,
		actor_id,
		BookWorkingDraftUpdate(expected_revision=1, content=draft),
	)

	chapters = sum(1 for node in draft.toc if node.kind == "chapter")
	texts = sum(1 for node in draft.toc if node.kind == "text")

	return RuleBookMigrationRead(
		book_id=created.book.id,
		system_id=system_id,
		draft_revision=saved.revision,
		chapters=chapters,
		texts=texts,
	)
