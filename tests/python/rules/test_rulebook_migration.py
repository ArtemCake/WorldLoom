# tests/python/rules/test_rulebook_migration.py

"""Перенос текстового раздела rulebook в черновик книги формата 2."""

import unittest

from backend.app.modules.rules.services.books.rulebook_migration import (
    rulebook_to_book_draft,
)


def chapter(label, fields, status="described"):
    return {"label": label, "status": status, "fields": fields}


class RulebookMigrationTests(unittest.TestCase):
    def test_empty_rulebook(self):
        draft = rulebook_to_book_draft({}, title="Пустая система")
        self.assertEqual(draft.toc, [])

        with self.assertRaises(ValueError):
            draft.ensure_publishable()

    def test_single_chapter_with_fields(self):
        rulebook = {"combat": chapter("Бой", {"attacks": "Текст атак", "defense": "Текст защиты"})}
        draft = rulebook_to_book_draft(rulebook, title="Правила боя", summary="Боевые правила")

        self.assertEqual(len(draft.toc), 3)
        self.assertEqual(draft.title, "Правила боя")
        self.assertEqual(draft.summary, "Боевые правила")

        nodes = {node.key: node for node in draft.toc}
        self.assertEqual(nodes["combat"].kind, "chapter")
        self.assertEqual(nodes["combat"].title, "Бой")
        self.assertEqual(nodes["combat"].parent_key, None)

        attacks = nodes["combat-attacks"]
        self.assertEqual(attacks.kind, "text")
        self.assertEqual(attacks.parent_key, "combat")
        self.assertEqual(attacks.content.body, "Текст атак")

        defense = nodes["combat-defense"]
        self.assertEqual(defense.kind, "text")
        self.assertEqual(defense.parent_key, "combat")
        self.assertEqual(defense.content.body, "Текст защиты")

    def test_empty_fields_are_skipped(self):
        rulebook = {
            "rest": chapter("Отдых", {
                "needs": "Нужен отдых",
                "unused_field": "",
                "draft_field": "   ",
                "none_field": None,
            })
        }
        draft = rulebook_to_book_draft(rulebook, title="Правила отдыха")

        texts = [n for n in draft.toc if n.kind == "text"]
        self.assertEqual(len(texts), 1)
        self.assertEqual(texts[0].content.body, "Нужен отдых")
        self.assertEqual(len(draft.toc), 2)

        draft.ensure_publishable()

    def test_chapter_without_text_becomes_chapter_only(self):
        rulebook = {"powers": chapter("Магия", {"access": "", "effects": ""})}
        draft = rulebook_to_book_draft(rulebook, title="Магия")

        self.assertEqual(len(draft.toc), 1)
        self.assertEqual(draft.toc[0].kind, "chapter")
        self.assertEqual(draft.toc[0].key, "powers")

    def test_slug_normalization_from_code(self):
        rulebook = {"Combat Rules!": chapter("Правила боя", {"Attack Roll": "Бросок атаки"})}
        draft = rulebook_to_book_draft(rulebook, title="Система")

        keys = [node.key for node in draft.toc]
        self.assertIn("combat-rules", keys)
        self.assertIn("combat-rules-attack-roll", keys)

        for node in draft.toc:
            self.assertRegex(node.key, r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")

    def test_missing_label_uses_code_as_title(self):
        rulebook = {"combat": chapter("", {"attacks": "Текст"})}
        draft = rulebook_to_book_draft(rulebook, title="Система")

        chapter_node = next(n for n in draft.toc if n.kind == "chapter")
        self.assertEqual(chapter_node.title, "combat")

    def test_key_collision_resolved(self):
        # Два разных кода, дающие одинаковый слаг после нормализации.
        rulebook = {
            "combat": chapter("Бой 1", {"attacks": "Первый"}),
            "Combat": chapter("Бой 2", {"attacks": "Второй"}),
        }
        draft = rulebook_to_book_draft(rulebook, title="Система")

        keys = [node.key for node in draft.toc]
        self.assertEqual(len(keys), len(set(keys)), "Ключи должны быть уникальны")

        texts = [n for n in draft.toc if n.kind == "text"]
        self.assertEqual(len(texts), 2)

    def test_position_is_ordered(self):
        rulebook = {
            "b": chapter("B", {"x": "1"}),
            "a": chapter("A", {"y": "2"}),
        }
        draft = rulebook_to_book_draft(rulebook, title="Система")

        chapters = [n for n in draft.toc if n.kind == "chapter"]
        self.assertEqual([n.key for n in chapters], ["a", "b"])
        self.assertEqual([n.position for n in chapters], [0, 1])

    def test_status_unused_still_transfers_nonempty_text(self):
        rulebook = {"optional": chapter("Необязательное", {"rule": "Правило есть"}, status="unused")}
        draft = rulebook_to_book_draft(rulebook, title="Система")

        texts = [n for n in draft.toc if n.kind == "text"]
        self.assertEqual(len(texts), 1)
        self.assertEqual(texts[0].content.body, "Правило есть")

    def test_language_and_edition_propagate(self):
        rulebook = {"combat": chapter("Бой", {"attacks": "Текст"})}
        draft = rulebook_to_book_draft(
            rulebook, title="Rules", language="en", edition_key="2014",
        )

        self.assertEqual(draft.language, "en")
        self.assertEqual(draft.edition_key, "2014")

        text = next(n for n in draft.toc if n.kind == "text")
        self.assertEqual(text.content.language, "en")
        self.assertEqual(text.content.edition_key, "2014")

    def test_invalid_rulebook_type(self):
        with self.assertRaises(TypeError):
            rulebook_to_book_draft([], title="Система")

        with self.assertRaises(TypeError):
            rulebook_to_book_draft("not a dict", title="Система")

    def test_invalid_chapter_type(self):
        with self.assertRaises(TypeError):
            rulebook_to_book_draft({"combat": "текст"}, title="Система")

    def test_invalid_fields_type(self):
        with self.assertRaises(TypeError):
            rulebook_to_book_draft({"combat": {"label": "Бой", "fields": "строка"}}, title="Система")

    def test_all_chapter_statuses_round_trip(self):
        rulebook = {
            "a": chapter("A", {"x": "1"}, status="described"),
            "b": chapter("B", {"y": "2"}, status="draft"),
            "c": chapter("C", {"z": "3"}, status="unused"),
        }
        draft = rulebook_to_book_draft(rulebook, title="Система")

        self.assertEqual(len(draft.toc), 6)
        draft.ensure_publishable()


if __name__ == "__main__":
    unittest.main()
