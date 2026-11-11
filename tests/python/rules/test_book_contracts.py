# tests/python/rules/test_book_contracts.py

"""Проверки содержания книг и структуры оглавления."""

import unittest

from uuid import uuid4

from pydantic import ValidationError

from backend.app.modules.rules.schemas import books as contracts


class BookContractTests(unittest.TestCase):
    def setUp(self):
        self.version_id = uuid4()

    def chapter(self, key="basics", parent=None, position=0):
        return {
            "kind": "chapter",
            "key": key,
            "parent_key": parent,
            "position": position,
            "title": "Основы",
        }

    def article(self, key="checks", parent="basics", position=0, version_id=None):
        return {
            "kind": "article",
            "key": key,
            "parent_key": parent,
            "position": position,
            "article_version_id": version_id or self.version_id,
        }

    def content(self, toc=None):
        return contracts.BookContent(
            title="Книга правил",
            edition_key="dnd5e-2014",
            toc=toc if toc is not None else [self.chapter(), self.article()],
        )

    def test_content_round_trip_preserves_structure(self):
        content = self.content()
        restored = contracts.BookContent.model_validate_json(content.model_dump_json())

        self.assertEqual(restored, content)
        self.assertIsInstance(restored.toc[0], contracts.BookChapterNode)
        self.assertIsInstance(restored.toc[1], contracts.BookArticleNode)
        restored.ensure_publishable()

    def test_empty_draft_is_allowed(self):
        content = self.content([])

        self.assertEqual(content.toc, [])
        self.assertEqual(content.article_version_ids(), frozenset())

    def test_empty_book_cannot_be_published(self):
        with self.assertRaises(ValueError):
            self.content([]).ensure_publishable()

    def test_chapters_without_articles_cannot_be_published(self):
        with self.assertRaises(ValueError):
            self.content([self.chapter()]).ensure_publishable()

    def test_root_article_is_allowed(self):
        content = self.content([self.article(parent=None)])

        content.ensure_publishable()
        self.assertEqual(content.article_version_ids(), frozenset({self.version_id}))

    def test_parent_can_follow_child_in_input(self):
        content = self.content([self.article(), self.chapter()])

        content.ensure_publishable()

    def test_duplicate_node_key_is_rejected(self):
        toc = [self.chapter(), self.article(key="basics")]

        with self.assertRaises(ValidationError):
            self.content(toc)

    def test_missing_parent_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.content([self.article(parent="missing")])

    def test_article_cannot_be_parent(self):
        toc = [
            self.article(key="first", parent=None),
            self.article(key="second", parent="first"),
        ]

        with self.assertRaises(ValidationError):
            self.content(toc)

    def test_self_reference_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.content([self.chapter(parent="basics")])

    def test_cycle_between_chapters_is_rejected(self):
        toc = [
            self.chapter(key="first", parent="second"),
            self.chapter(key="second", parent="first"),
        ]

        with self.assertRaises(ValidationError):
            self.content(toc)

    def test_duplicate_sibling_position_is_rejected(self):
        toc = [
            self.chapter(),
            self.article(key="first"),
            self.article(key="second"),
        ]

        with self.assertRaises(ValidationError):
            self.content(toc)

    def test_same_position_under_different_parents_is_allowed(self):
        toc = [
            self.chapter(key="first", position=0),
            self.chapter(key="second", position=1),
            self.article(key="first-article", parent="first", position=0),
            self.article(key="second-article", parent="second", position=0),
        ]

        self.content(toc).ensure_publishable()

    def test_position_gaps_are_allowed(self):
        toc = [
            self.article(key="first", parent=None, position=10),
            self.article(key="second", parent=None, position=30),
        ]

        self.content(toc).ensure_publishable()

    def test_position_must_be_nonnegative_integer(self):
        for value in (-1, True, "0", 0.5):
            with self.subTest(value=value):
                node = self.article(parent=None)
                node["position"] = value

                with self.assertRaises(ValidationError):
                    self.content([node])

    def test_article_requires_publication_identifier(self):
        node = self.article(parent=None)
        del node["article_version_id"]

        with self.assertRaises(ValidationError):
            self.content([node])

    def test_live_article_identifier_cannot_replace_publication(self):
        node = self.article(parent=None)
        del node["article_version_id"]
        node["article_id"] = uuid4()

        with self.assertRaises(ValidationError):
            self.content([node])

    def test_chapter_cannot_contain_publication_identifier(self):
        node = self.chapter()
        node["article_version_id"] = self.version_id

        with self.assertRaises(ValidationError):
            self.content([node])

    def test_same_publication_can_appear_twice(self):
        toc = [
            self.article(key="first", parent=None, position=0),
            self.article(key="second", parent=None, position=1),
        ]
        content = self.content(toc)

        content.ensure_publishable()
        self.assertEqual(len(content.toc), 2)
        self.assertEqual(content.article_version_ids(), frozenset({self.version_id}))

    def test_different_publications_remain_distinct_dependencies(self):
        another_version_id = uuid4()
        toc = [
            self.article(key="first", parent=None, position=0),
            self.article(key="second", parent=None, position=1, version_id=another_version_id),
        ]

        self.assertEqual(self.content(toc).article_version_ids(), frozenset({self.version_id, another_version_id}))

    def test_optional_navigation_title_is_preserved(self):
        node = self.article(parent=None)
        node["title"] = "Как выполнить проверку"
        content = self.content([node])

        self.assertEqual(content.toc[0].title, "Как выполнить проверку")

    def test_blank_titles_are_rejected(self):
        for node in (self.chapter(), self.article(parent=None)):
            with self.subTest(kind=node["kind"]):
                node["title"] = "   "

                with self.assertRaises(ValidationError):
                    self.content([node])

    def test_unknown_node_kind_is_rejected(self):
        node = self.chapter()
        node["kind"] = "script"

        with self.assertRaises(ValidationError):
            self.content([node])

    def test_unknown_content_field_is_rejected(self):
        payload = self.content().model_dump(mode="python")
        payload["executable_script"] = "unexpected"

        with self.assertRaises(ValidationError):
            contracts.BookContent.model_validate(payload)

    def test_invalid_schema_version_is_rejected(self):
        for value in (2, True, "1", 1.0):
            with self.subTest(value=value):
                payload = self.content().model_dump(mode="python")
                payload["schema_version"] = value

                with self.assertRaises(ValidationError):
                    contracts.BookContent.model_validate(payload)

    def test_excessive_depth_is_rejected(self):
        toc = []
        parent = None

        for number in range(contracts.MAX_TOC_DEPTH):
            key = f"chapter-{number}"
            toc.append(self.chapter(key=key, parent=parent))
            parent = key

        toc.append(self.article(parent=parent))

        with self.assertRaises(ValidationError):
            self.content(toc)

    def test_publish_revalidates_mutated_content(self):
        content = self.content()
        content.toc[0].parent_key = "missing"

        with self.assertRaises(ValueError):
            content.ensure_publishable()

    def test_draft_update_requires_valid_revision(self):
        for revision in (0, -1, True, "1"):
            with self.subTest(revision=revision):
                with self.assertRaises(ValidationError):
                    contracts.RuleBookDraftUpdate(expected_revision=revision, content=self.content())

    def test_publish_request_does_not_accept_replacement_content(self):
        payload = {
            "expected_revision": 1,
            "content": self.content().model_dump(mode="python"),
        }

        with self.assertRaises(ValidationError):
            contracts.RuleBookPublish.model_validate(payload)

    def test_custom_category_is_allowed(self):
        payload = self.content().model_dump(mode="python")
        payload["category"] = "world-travel"

        content = contracts.BookContent.model_validate(payload)

        self.assertEqual(content.category, "world-travel")


if __name__ == "__main__":
    unittest.main()
