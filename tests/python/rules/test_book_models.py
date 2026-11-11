# tests/python/rules/test_book_models.py

"""Проверки регистрации и ORM-описания книг."""

import unittest

from sqlalchemy.dialects.postgresql import dialect
from sqlalchemy.schema import CreateTable

from backend.app.infrastructure.database.model_registry import configure_models
from backend.app.modules.rules.models.books import RuleBook, RuleBookDraft, RuleBookVersion, RuleBookVersionArticle


class BookModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metadata = configure_models()

    def test_tables_are_registered(self):
        names = ("rule_books", "rule_book_drafts", "rule_book_versions", "rule_book_version_articles")

        for name in names:
            with self.subTest(table=name):
                self.assertIn(name, self.metadata.tables)

    def test_models_use_registered_metadata(self):
        for model in (RuleBook, RuleBookDraft, RuleBookVersion, RuleBookVersionArticle):
            with self.subTest(model=model.__name__):
                self.assertIs(model.__table__.metadata, self.metadata)

    def test_draft_has_revision_control(self):
        self.assertIs(RuleBookDraft.__mapper__.version_id_col, RuleBookDraft.__table__.c.revision)

    def test_version_has_unique_number_and_source_revision(self):
        names = {constraint.name for constraint in RuleBookVersion.__table__.constraints}

        self.assertIn("uq_rule_book_versions_number", names)
        self.assertIn("uq_rule_book_versions_source", names)

    def test_dependency_has_composite_primary_key(self):
        names = {column.name for column in RuleBookVersionArticle.__table__.primary_key.columns}

        self.assertEqual(names, {"book_version_id", "article_version_id"})

    def test_dependency_foreign_keys_restrict_deletion(self):
        references = RuleBookVersionArticle.__table__.foreign_keys
        targets = {reference.target_fullname for reference in references}

        self.assertEqual(targets, {"rule_book_versions.id", "rule_article_versions.id"})
        self.assertTrue(all(reference.ondelete == "RESTRICT" for reference in references))

    def test_tables_compile_for_postgresql(self):
        for model in (RuleBook, RuleBookDraft, RuleBookVersion, RuleBookVersionArticle):
            with self.subTest(model=model.__name__):
                statement = str(CreateTable(model.__table__).compile(dialect=dialect()))

                self.assertIn("CREATE TABLE", statement)
                self.assertIn(model.__tablename__, statement)


if __name__ == "__main__":
    unittest.main()
