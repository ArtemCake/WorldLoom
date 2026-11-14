# tests/python/rules/test_book_draft_content.py

"""Проверки собственных текстов, преобразования черновика и сборки публикации."""

import unittest
from datetime import datetime, timezone
from uuid import uuid4
from pydantic import ValidationError
from backend.app.modules.rules.schemas import book_draft_content as contracts
from backend.app.modules.rules.schemas.articles import ArticleContent, RuleArticleVersionRead
from backend.app.modules.rules.schemas.books import BookContent
from backend.app.modules.rules.services.book_draft_commands import apply_book_text_command, read_book_draft_content
from backend.app.modules.rules.services.book_draft_publication import collect_owned_texts, compile_book_publication


class BookDraftContentTests(unittest.TestCase):
	def setUp(self):
		self.external_id = uuid4()
		self.actor_id = uuid4()
		self.external = {
			"kind": "article",
			"key": "external",
			"parent_key": None,
			"position": 0,
			"title": "Название внешнего раздела",
			"article_version_id": self.external_id,
		}
		self.previous = BookContent(title="Книга", introduction="Введение", toc=[self.external])

	def text_node(self, key="own", position=1, parent=None, body="Текст", title=None):
		data = {
			"key": key,
			"position": position,
			"parent_key": parent,
			"title": title,
			"content": ArticleContent(title="Собственный раздел", body=body),
		}
		return contracts.BookTextNode(**data)

	def draft(self, nodes=None):
		content = read_book_draft_content(self.previous)
		payload = content.model_dump(mode="python")
		own = self.text_node()
		payload["toc"] = nodes if nodes is not None else [self.external, own.model_dump(mode="python")]
		return contracts.BookDraftContent.model_validate(payload)

	def publication(self, node, article_id=None, version_id=None):
		data = {
			"id": version_id or uuid4(),
			"article_id": article_id or uuid4(),
			"version_number": 1,
			"source_draft_revision": 1,
			"content_json": node.content.model_dump(mode="python"),
			"published_by": self.actor_id,
			"published_at": datetime(2026, 11, 14, tzinfo=timezone.utc),
		}
		return RuleArticleVersionRead(**data)

	def test_explicit_upgrade_preserves_previous_content(self):
		before = self.previous.model_dump(mode="json")
		upgraded = read_book_draft_content(self.previous)
		expected = dict(before)
		expected["schema_version"] = 2

		self.assertEqual(upgraded.model_dump(mode="json"), expected)
		self.assertEqual(self.previous.model_dump(mode="json"), before)
		self.assertEqual(self.previous.schema_version, 1)

	def test_unknown_and_noninteger_versions_are_rejected(self):
		for version in (True, "2", 3, None):
			payload = self.previous.model_dump(mode="python")
			payload["schema_version"] = version

			with self.subTest(version=version):
				with self.assertRaises(ValueError):
					read_book_draft_content(payload)

	def test_missing_version_is_not_guessed(self):
		payload = self.previous.model_dump(mode="python")
		del payload["schema_version"]

		with self.assertRaises(ValueError):
			read_book_draft_content(payload)

	def test_new_content_round_trip(self):
		content = self.draft()
		restored = contracts.BookDraftContent.model_validate_json(content.model_dump_json())

		self.assertEqual(restored, content)
		self.assertIsInstance(restored.toc[1], contracts.BookTextNode)
		self.assertEqual(restored.article_version_ids(), frozenset({self.external_id}))

	def test_old_publication_contract_rejects_new_draft(self):
		with self.assertRaises(ValidationError):
			BookContent.model_validate(self.draft().model_dump(mode="python"))

	def test_add_preserves_book_and_external_material(self):
		before = self.previous.model_dump(mode="json")
		command = contracts.AddBookText(node=self.text_node())
		result = apply_book_text_command(self.previous, command)

		self.assertEqual(len(result.toc), 2)
		self.assertEqual(result.toc[0].model_dump(mode="json"), before["toc"][0])
		self.assertEqual(result.introduction, self.previous.introduction)
		self.assertEqual(self.previous.model_dump(mode="json"), before)

	def test_duplicate_key_is_rejected(self):
		command = contracts.AddBookText(node=self.text_node(key="external"))

		with self.assertRaises(ValueError):
			apply_book_text_command(self.previous, command)

	def test_duplicate_position_is_rejected(self):
		command = contracts.AddBookText(node=self.text_node(position=0))

		with self.assertRaises(ValidationError):
			apply_book_text_command(self.previous, command)

	def test_missing_parent_is_rejected(self):
		command = contracts.AddBookText(node=self.text_node(parent="missing"))

		with self.assertRaises(ValidationError):
			apply_book_text_command(self.previous, command)

	def test_text_cannot_be_parent(self):
		first = self.text_node()
		second = self.text_node(key="child", position=0, parent="own")
		source = self.draft()
		command = contracts.AddBookText(node=second)

		with self.assertRaises(ValidationError):
			apply_book_text_command(source, command)

		self.assertEqual(source.toc[1], first)

	def test_update_preserves_location_and_custom_title(self):
		chapter = {"kind": "chapter", "key": "main", "position": 0, "title": "Глава"}
		own = self.text_node(position=7, parent="main", title="Название в оглавлении")
		source = self.draft([chapter, own.model_dump(mode="python")])
		content = ArticleContent(title="Новое название текста", body="Новый текст")
		command = contracts.UpdateBookText(key="own", content=content)
		result = apply_book_text_command(source, command)
		updated = result.toc[1]

		self.assertEqual(updated.key, own.key)
		self.assertEqual(updated.parent_key, "main")
		self.assertEqual(updated.position, 7)
		self.assertEqual(updated.title, "Название в оглавлении")
		self.assertEqual(updated.content.body, "Новый текст")
		self.assertEqual(source.toc[1].content.body, "Текст")

	def test_external_material_cannot_be_edited_as_owned_text(self):
		content = ArticleContent(title="Подмена", body="Не применять")
		command = contracts.UpdateBookText(key="external", content=content)

		with self.assertRaises(ValueError):
			apply_book_text_command(self.draft(), command)

	def test_remove_preserves_other_nodes(self):
		source = self.draft()
		command = contracts.RemoveBookText(key="own")
		result = apply_book_text_command(source, command)

		self.assertEqual(len(result.toc), 1)
		self.assertEqual(result.toc[0], source.toc[0])
		self.assertEqual(len(source.toc), 2)

	def test_missing_text_is_not_created_by_update(self):
		content = ArticleContent(title="Раздел", body="Текст")
		command = contracts.UpdateBookText(key="missing", content=content)

		with self.assertRaises(ValueError):
			apply_book_text_command(self.draft(), command)

	def test_mutated_command_is_revalidated(self):
		command = contracts.AddBookText(node=self.text_node())
		command.node.position = -1

		with self.assertRaises(ValidationError):
			apply_book_text_command(self.previous, command)

	def test_empty_text_can_exist_in_draft_but_blocks_publication(self):
		own = self.text_node(body="   ")
		content = self.draft([own.model_dump(mode="python")])

		self.assertEqual(content.toc[0].content.body, "   ")

		with self.assertRaises(ValueError):
			content.ensure_publishable()

	def test_owned_texts_are_independent_copies(self):
		source = self.draft()
		texts = collect_owned_texts(source)
		texts["own"].body = "Изменённая копия"

		self.assertEqual(source.toc[1].content.body, "Текст")

	def test_compile_preserves_metadata_and_external_nodes(self):
		payload = self.draft().model_dump(mode="python")
		payload["sources"] = [{"title": "Источник книги"}]
		source = contracts.BookDraftContent.model_validate(payload)
		own = source.toc[1]
		version = self.publication(own)
		before = source.model_dump(mode="json")
		result = compile_book_publication(source, {"own": version})

		self.assertEqual(result.schema_version, 1)
		self.assertEqual(result.toc[0], source.toc[0])
		self.assertEqual(result.toc[1].article_version_id, version.id)
		self.assertEqual(result.toc[1].key, own.key)
		self.assertEqual(result.toc[1].title, own.title)
		self.assertEqual(result.sources, source.sources)
		self.assertEqual(result.introduction, source.introduction)
		self.assertEqual(source.model_dump(mode="json"), before)
		self.assertEqual(result.article_version_ids(), frozenset({self.external_id, version.id}))

	def test_compile_requires_exact_owned_text_set(self):
		source = self.draft()
		version = self.publication(source.toc[1])

		for mapping in ({}, {"own": version, "extra": version}):
			with self.subTest(keys=list(mapping)):
				with self.assertRaises(ValueError):
					compile_book_publication(source, mapping)

	def test_compile_rejects_changed_publication_content(self):
		source = self.draft()
		version = self.publication(source.toc[1])
		version.content_json.body = "Другой текст"

		with self.assertRaises(ValueError):
			compile_book_publication(source, {"own": version})

	def test_compile_compares_sources_too(self):
		source = self.draft()
		version = self.publication(source.toc[1])
		payload = version.model_dump(mode="python")
		payload["content_json"]["sources"] = [{"title": "Другой источник"}]
		version = RuleArticleVersionRead.model_validate(payload)

		with self.assertRaises(ValueError):
			compile_book_publication(source, {"own": version})

	def test_compile_rejects_external_version_as_owned(self):
		source = self.draft()
		version = self.publication(source.toc[1], version_id=self.external_id)

		with self.assertRaises(ValueError):
			compile_book_publication(source, {"own": version})

	def test_independent_texts_cannot_share_article(self):
		first = self.text_node()
		second = self.text_node(key="second", position=2)
		nodes = [first.model_dump(mode="python"), second.model_dump(mode="python")]
		source = self.draft(nodes)
		article_id = uuid4()
		versions = {
			"own": self.publication(first, article_id=article_id),
			"second": self.publication(second, article_id=article_id),
		}

		with self.assertRaises(ValueError):
			compile_book_publication(source, versions)

	def test_external_only_content_compiles_without_owned_publications(self):
		source = read_book_draft_content(self.previous)
		result = compile_book_publication(source, {})

		self.assertEqual(result, self.previous)

	def test_empty_book_is_not_publishable(self):
		source = self.draft([])

		with self.assertRaises(ValueError):
			compile_book_publication(source, {})


if __name__ == "__main__":
	unittest.main()