# tests/python/rules/test_article_foundation.py

"""Проверка контрактов и ORM-описания самостоятельных статей."""

import unittest

from pydantic import ValidationError
from sqlalchemy.dialects.postgresql import dialect
from sqlalchemy.schema import CreateTable

from backend.app.infrastructure.database.model_registry import configure_models
from backend.app.modules.rules.models.articles import RuleArticle, RuleArticleDraft, RuleArticleVersion
from backend.app.modules.rules.schemas.articles import ArticleContent, RuleArticleCreate, RuleArticleDraftUpdate


class ArticleContractTests(unittest.TestCase):
    def make_content(self) -> ArticleContent:
        return ArticleContent(title="Проверки характеристик", body="Описание правила.", edition_key="dnd5e-2014")

    def test_content_round_trip(self):
        content = self.make_content()
        restored = ArticleContent.model_validate_json(content.model_dump_json())

        self.assertEqual(restored, content)
        restored.ensure_publishable()

    def test_blank_title_is_rejected(self):
        with self.assertRaises(ValidationError):
            ArticleContent(title="   ")

    def test_empty_draft_is_allowed(self):
        content = ArticleContent(title="Новая статья")

        self.assertEqual(content.body, "")

    def test_empty_article_cannot_be_published(self):
        content = ArticleContent(title="Новая статья", body=" \n\t ")

        with self.assertRaises(ValueError):
            content.ensure_publishable()

    def test_unknown_field_is_rejected(self):
        payload = self.make_content().model_dump()
        payload["executable_script"] = "unexpected"

        with self.assertRaises(ValidationError):
            ArticleContent.model_validate(payload)

    def test_unsupported_schema_is_rejected(self):
        payload = self.make_content().model_dump()
        payload["schema_version"] = 2

        with self.assertRaises(ValidationError):
            ArticleContent.model_validate(payload)

    def test_revision_must_be_positive_integer(self):
        for revision in (0, -1, True, "1"):
            with self.subTest(revision=revision):
                with self.assertRaises(ValidationError):
                    RuleArticleDraftUpdate(expected_revision=revision, content=self.make_content())

    def test_invalid_slug_is_rejected(self):
        with self.assertRaises(ValidationError):
            RuleArticleCreate(slug="Некорректный код", content=self.make_content())

    def test_script_url_is_rejected(self):
        payload = self.make_content().model_dump()
        payload["sources"] = [{"title": "Источник", "url": "javascript:alert(1)"}]

        with self.assertRaises(ValidationError):
            ArticleContent.model_validate(payload)

    def test_markdown_is_not_rewritten(self):
        body = "# Заголовок\n\n| Параметр | Значение |\n|---|---|\n| Сложность | 15 |\n"
        content = ArticleContent(title="Пример", body=body)

        self.assertEqual(content.body, body)


class ArticleModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metadata = configure_models()

    def test_new_tables_are_registered(self):
        for name in ("rule_articles", "rule_article_drafts", "rule_article_versions"):
            with self.subTest(table=name):
                self.assertIn(name, self.metadata.tables)

    def test_models_use_registered_metadata(self):
        for model in (RuleArticle, RuleArticleDraft, RuleArticleVersion):
            with self.subTest(model=model.__name__):
                self.assertIs(model.__table__.metadata, self.metadata)

    def test_draft_has_revision_control(self):
        self.assertIs(RuleArticleDraft.__mapper__.version_id_col, RuleArticleDraft.__table__.c.revision)

    def test_publication_has_required_unique_constraints(self):
        names = {constraint.name for constraint in RuleArticleVersion.__table__.constraints}

        self.assertIn("uq_rule_article_versions_number", names)
        self.assertIn("uq_rule_article_versions_source", names)

    def test_article_reference_restricts_deletion(self):
        reference = next(iter(RuleArticleVersion.__table__.c.article_id.foreign_keys))

        self.assertEqual(reference.target_fullname, "rule_articles.id")
        self.assertEqual(reference.ondelete, "RESTRICT")

    def test_tables_compile_for_postgresql(self):
        for model in (RuleArticle, RuleArticleDraft, RuleArticleVersion):
            with self.subTest(model=model.__name__):
                statement = str(CreateTable(model.__table__).compile(dialect=dialect()))

                self.assertIn("CREATE TABLE", statement)
                self.assertIn(model.__tablename__, statement)


if __name__ == "__main__":
    unittest.main()
