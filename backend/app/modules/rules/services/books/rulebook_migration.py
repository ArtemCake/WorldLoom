# backend/app/modules/rules/services/books/rulebook_migration.py

"""Перенос текстового раздела rulebook в черновик книги формата 2.

rulebook хранится внутри числового профиля системы как раздел
``rulebook: {код: {label, status, fields: {код: текст}}}``.
Каждая глава становится главой книги, каждое поле — собственным
текстом книги. Числовая часть профиля при этом не изменяется.

Функции модуля чистые: не обращаются к БД и не проверяют права.
"""

from __future__ import annotations
import re
from typing import Any, Mapping

from backend.app.modules.rules.schemas.books.book_draft_content import (
    BookDraftContent,
    BookTextNode,
)
from backend.app.modules.rules.schemas.articles import ArticleContent
from backend.app.modules.rules.schemas.books import books as book_contracts


_SLUG_SAFE = re.compile(r"[^a-z0-9]+")

def _to_slug(code: str, *, fallback: str) -> str:
	"""Преобразовать код раздела в допустимый ключ оглавления."""
	normalized = _SLUG_SAFE.sub("-", code.strip().lower()).strip("-")

	if not normalized:
		normalized = fallback

	# Ключ должен начинаться с буквы или цифры и не превышать 100 символов.
	if not normalized[0].isalnum():
		normalized = f"{fallback}-{normalized}".strip("-")

	return normalized[:100]

def _chapter_title(chapter: Mapping[str, Any], code: str) -> str:
	"""Человекочитаемое название главы; запасной вариант — сам код."""
	label = chapter.get("label")

	if isinstance(label, str) and label.strip():
		return label.strip()[:200]

	return code[:200]

def rulebook_to_book_draft(
	rulebook: Mapping[str, Any],
	*,
	title: str,
	summary: str = "",
	language: str = "ru",
	edition_key: str | None = None,
) -> BookDraftContent:
	"""Собрать черновик книги формата 2 из раздела rulebook.

	Пустой rulebook даёт пустое оглавление: черновик книги при этом
	остаётся корректным, но не публикуется до появления текстов.
	"""

	if not isinstance(rulebook, Mapping):
		raise TypeError("rulebook должен быть словарём глав")

	used_keys: set[str] = set()
	toc: list[dict[str, Any]] = []

	for chapter_index, (raw_code, raw_chapter) in enumerate(sorted(rulebook.items())):
		if not isinstance(raw_chapter, Mapping):
			raise TypeError(f"Глава {raw_code!r} имеет неподдерживаемый формат")

		chapter_code = str(raw_code)
		chapter_key = _to_slug(chapter_code, fallback=f"chapter-{chapter_index}")

		if chapter_key in used_keys:
			chapter_key = f"{chapter_key}-{chapter_index}"[:100]

		used_keys.add(chapter_key)

		toc.append({
			"kind": "chapter",
			"key": chapter_key,
			"parent_key": None,
			"position": chapter_index,
			"title": _chapter_title(raw_chapter, chapter_code),
		})

		fields = raw_chapter.get("fields") or {}

		if not isinstance(fields, Mapping):
			raise TypeError(f"Поля главы {raw_code!r} имеют неподдержимый формат")

		for field_index, (raw_field, raw_text) in enumerate(sorted(fields.items())):
			field_code = str(raw_field)

			# Пустое поле rulebook не несёт текста и не должно становиться
			# непубликуемым собственным текстом книги.
			if not isinstance(raw_text, str) or not raw_text.strip():
				continue

			text_key = _to_slug(f"{chapter_key}-{field_code}", fallback=f"{chapter_key}-text")

			if text_key in used_keys:
				text_key = f"{text_key}-{field_index}"[:100]

			used_keys.add(text_key)

			content = ArticleContent(
				title=field_code[:200] or "Раздел",
				body=raw_text,
				language=language,
				edition_key=edition_key,
			)

			node = BookTextNode(
				key=text_key,
				parent_key=chapter_key,
				position=field_index,
				title=field_code[:200] or "Раздел",
				content=content,
			)
			toc.append(node.model_dump(mode="python"))

	return BookDraftContent(
		title=title[:200] or "Правила системы",
		summary=summary,
		language=language,
		edition_key=edition_key,
		toc=[book_contracts.BookChapterNode.model_validate(node) if node["kind"] == "chapter" else BookTextNode.model_validate(node) for node in toc],
	)
