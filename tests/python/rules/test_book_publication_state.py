# tests/python/rules/test_book_publication_state.py

"""Сравнение содержания без подключения к PostgreSQL."""

import unittest
from uuid import uuid4
from backend.app.modules.rules import errors
from backend.app.modules.rules.schemas.articles import ArticleContent
from backend.app.modules.rules.schemas.books.books import BookContent
from backend.app.modules.rules.schemas.books.book_draft_content import BookDraftContent
from backend.app.modules.rules.services.books.book_publication_state import book_content_changed, restore_publication_content


class BookPublicationStateTests(unittest.TestCase):
	def setUp(self):
		self.book_id = uuid4()
		self.version_id = uuid4()
		self.external_id = uuid4()
		self.text = ArticleContent(
			title="Собственный текст",
			body="Первая редакция.",
			sources=[{"title": "Источник раздела"}],
		)
		self.draft = BookDraftContent(
			title="Книга",
			introduction="Введение.",
			sources=[{"title": "Источник книги"}],
			toc=[
				{
					"kind": "text",
					"key": "own-text",
					"parent_key": None,
					"position": 0,
					"title": "Название в оглавлении",
					"content": self.text,
				},
				{
					"kind": "article",
					"key": "external-text",
					"parent_key": None,
					"position": 1,
					"article_version_id": self.external_id,
				},
			],
		)

		payload = self.draft.model_dump(mode="python")
		payload["schema_version"] = 1
		node = payload["toc"][0]
		node.pop("content")
		node["kind"] = "article"
		node["article_version_id"] = self.version_id

		self.publication = BookContent.model_validate(payload)
		self.snapshots = {
			self.version_id: {
				"book_id": self.book_id,
				"node_key": "own-text",
				"content_json": self.text.model_dump(mode="json"),
			},
		}

	def changed(self, draft=None, snapshots=None):
		return book_content_changed(
			self.book_id,
			self.draft if draft is None else draft,
			self.publication,
			self.snapshots if snapshots is None else snapshots,
		)

	def modified(self, change):
		payload = self.draft.model_dump(mode="python")
		change(payload)
		return BookDraftContent.model_validate(payload)

	def test_materialized_publication_matches_working_content(self):
		self.assertFalse(self.changed())

	def test_unpublished_book_has_changes(self):
		self.assertTrue(book_content_changed(self.book_id, self.draft, None, {}))

	def test_changed_owned_body_is_detected(self):
		draft = self.modified(lambda data: data["toc"][0]["content"].update(body="Новая редакция."))
		self.assertTrue(self.changed(draft))

	def test_empty_owned_body_is_a_valid_unpublished_change(self):
		draft = self.modified(lambda data: data["toc"][0]["content"].update(body=""))
		self.assertTrue(self.changed(draft))

	def test_changed_owned_sources_are_detected(self):
		draft = self.modified(lambda data: data["toc"][0]["content"].update(sources=[]))
		self.assertTrue(self.changed(draft))

	def test_changed_book_sources_are_detected(self):
		draft = self.modified(lambda data: data.update(sources=[]))
		self.assertTrue(self.changed(draft))

	def test_changed_external_version_is_detected(self):
		draft = self.modified(lambda data: data["toc"][1].update(article_version_id=uuid4()))
		self.assertTrue(self.changed(draft))

	def test_array_order_does_not_replace_explicit_positions(self):
		draft = self.modified(lambda data: data["toc"].reverse())
		self.assertFalse(self.changed(draft))

	def test_changed_reading_positions_are_detected(self):
		def swap(data):
			data["toc"][0]["position"] = 1
			data["toc"][1]["position"] = 0

		self.assertTrue(self.changed(self.modified(swap)))

	def test_foreign_internal_binding_is_storage_error(self):
		snapshots = {key: dict(value) for key, value in self.snapshots.items()}
		snapshots[self.version_id]["book_id"] = uuid4()

		with self.assertRaises(errors.RuleBookStorageError):
			self.changed(snapshots=snapshots)

	def test_wrong_internal_node_key_is_storage_error(self):
		snapshots = {key: dict(value) for key, value in self.snapshots.items()}
		snapshots[self.version_id]["node_key"] = "another-text"

		with self.assertRaises(errors.RuleBookStorageError):
			self.changed(snapshots=snapshots)

	def test_restore_does_not_modify_publication_or_snapshot(self):
		before_publication = self.publication.model_dump(mode="json")
		before_text = self.text.model_dump(mode="json")

		restored = restore_publication_content(self.book_id, self.publication, self.snapshots)
		restored.toc[0].content.body = "Локальное изменение."

		self.assertEqual(self.publication.model_dump(mode="json"), before_publication)
		self.assertEqual(self.snapshots[self.version_id]["content_json"], before_text)

	def test_legacy_content_matches_after_format_conversion(self):
		payload = self.publication.model_dump(mode="python")
		payload["toc"] = [payload["toc"][1]]
		legacy = BookContent.model_validate(payload)

		working = legacy.model_dump(mode="python")
		working["schema_version"] = 2
		draft = BookDraftContent.model_validate(working)

		self.assertFalse(book_content_changed(self.book_id, draft, legacy, {}))


if __name__ == "__main__":
	unittest.main()
