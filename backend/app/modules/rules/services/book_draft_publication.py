# backend/app/modules/rules/services/book_draft_publication.py

"""Сборка снимка книги из черновика и подготовленных публикаций собственных текстов.

Модуль не создаёт записи, не проверяет доступ и не управляет транзакцией.
Публикации должен передать серверный слой после записи и чтения в общей транзакции.
"""

from collections.abc import Mapping
from backend.app.modules.rules.schemas import book_draft_content as contracts
from backend.app.modules.rules.schemas.articles import ArticleContent, RuleArticleVersionRead
from backend.app.modules.rules.schemas.books import BookContent
from backend.app.modules.rules.services.book_draft_commands import read_book_draft_content


DraftContent = contracts.BookDraftContent
VersionRead = RuleArticleVersionRead

def collect_owned_texts(value: DraftContent) -> dict[str, ArticleContent]:
	"""Получить независимые копии собственных текстов по ключам оглавления."""

	content = read_book_draft_content(value)
	return {node.key: node.content.model_copy(deep=True) for node in content.toc if isinstance(node, contracts.BookTextNode)}

def compile_book_publication(value: DraftContent, publications: Mapping[str, VersionRead]) -> BookContent:
	"""Заменить собственные тексты точными публикациями и получить прежний формат снимка."""

	content = read_book_draft_content(value)
	content.ensure_publishable()

	if not isinstance(publications, Mapping):
		raise TypeError("Требуется соответствие собственных текстов и их публикаций")

	owned = collect_owned_texts(content)

	if set(publications) != set(owned):
		raise ValueError("Состав публикаций не соответствует собственным текстам книги")

	external_ids = content.article_version_ids()
	version_ids = set()
	article_ids = set()
	checked_versions = {}

	for key, expected in owned.items():
		supplied = publications[key]

		if not isinstance(supplied, VersionRead):
			raise TypeError("Требуется проверенный контракт публикации текста")

		version = VersionRead.model_validate(supplied.model_dump(mode="python"))

		if version.content_json.model_dump(mode="json") != expected.model_dump(mode="json"):
			raise ValueError("Содержание публикации отличается от собственного текста книги")

		if version.id in external_ids or version.id in version_ids:
			raise ValueError("Публикация собственного текста использована неоднозначно")

		if version.article_id in article_ids:
			raise ValueError("Независимые собственные тексты связаны с одной статьёй")

		version_ids.add(version.id)
		article_ids.add(version.article_id)
		checked_versions[key] = version

	payload = content.model_dump(mode="python")
	payload["schema_version"] = 1

	for index, node in enumerate(content.toc):
		if not isinstance(node, contracts.BookTextNode):
			continue

		replacement = {
			"kind": "article",
			"key": node.key,
			"parent_key": node.parent_key,
			"position": node.position,
			"title": node.title,
			"article_version_id": checked_versions[node.key].id,
		}
		payload["toc"][index] = replacement

	publication = BookContent.model_validate(payload)
	publication.ensure_publishable()
	return publication