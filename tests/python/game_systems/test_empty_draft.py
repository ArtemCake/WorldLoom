# tests/python/game_systems/test_empty_draft.py

"""Создание системы без профиля правил.

Новая схема конструктора разрешает создание черновика системы
без заполненных числовых правил (раздел 3.1 v2.0).
"""

import unittest

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from backend.app.modules.game_systems.schemas.game_system_editor import (
    GameSystemEditorCreate,
    GameSystemEditorRead,
)
from backend.app.modules.game_systems.services import editor_service as service


def make_session(results: list):
    return SimpleNamespace(
        new=(), dirty=(), deleted=(), execute=AsyncMock(side_effect=results)
    )


def row_result(row: dict):
    result = MagicMock()
    result.mappings.return_value.one.return_value = row
    result.mappings.return_value.one_or_none.return_value = row
    return result


def unique_check_result():
    """Результат проверки уникальности: совпадений нет."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    return result


class EmptyDraftCreationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.actor_id = uuid4()
        self.system_id = uuid4()
        self.now = datetime.now(timezone.utc)

    def _make_system_row(self, system_id=None, is_active=False):
        return {
            "id": system_id or self.system_id,
            "name": "Тест без правил",
            "slug": "empty-draft-test",
            "rules_engine_version": "1.0",
            "description": None,
            "is_active": is_active,
            "created_at": self.now,
            "updated_at": self.now,
        }

    def _make_draft_row(self, system_id, rules_json, revision=1):
        return {
            "id": uuid4(),
            "system_id": system_id,
            "rules_json": rules_json,
            "revision": revision,
            "created_at": self.now,
            "updated_at": self.now,
        }

    def test_create_schema_accepts_rules_none(self):
        data = {
            "system": {
                "name": "Система без правил",
                "slug": "no-rules",
                "description": None,
                "is_active": False,
                "rules_engine_version": "1.0",
            },
            "rules": None,
        }
        instance = GameSystemEditorCreate.model_validate(data)
        self.assertIsNone(instance.rules)

    def test_create_schema_accepts_missing_rules(self):
        data = {
            "system": {
                "name": "Система без правил",
                "slug": "no-rules-missing",
                "description": None,
                "is_active": False,
                "rules_engine_version": "1.0",
            },
        }
        instance = GameSystemEditorCreate.model_validate(data)
        self.assertIsNone(instance.rules)

    async def test_create_with_empty_draft(self):
        system = self._make_system_row()
        draft = self._make_draft_row(
            system["id"],
            {
                "schema_version": 4,
                "calculations": {"attributes": {}, "derived": {}},
                "initial_attributes": {},
                "resources": {},
            },
            revision=1,
        )

        session = make_session([
            unique_check_result(),  # check unique
            row_result(system),  # insert systems -> returning
            row_result(draft),   # insert drafts -> returning
        ])
        session.execute.return_value.scalar_one_or_none.return_value = None

        result = await service.create_system_with_draft(session, GameSystemEditorCreate(
            system={
                "name": "Система без правил",
                "slug": "empty-draft",
                "description": None,
                "is_active": False,
                "rules_engine_version": "1.0",
            },
            rules=None,
        ))

        self.assertIsInstance(result, GameSystemEditorRead)
        self.assertEqual(result.system.id, system["id"])
        self.assertFalse(result.system.is_active)
        self.assertIsNotNone(result.draft)
        self.assertEqual(result.draft.revision, 1)
        self.assertEqual(result.draft.rules.schema_version, 4)
        self.assertEqual(result.draft.rules.calculations.attributes, {})

    async def test_create_with_full_profile(self):
        system = self._make_system_row(is_active=True)
        draft = self._make_draft_row(
            system["id"],
            {
                "schema_version": 4,
                "calculations": {
                    "attributes": {
                        "level": {
                            "label": "Уровень",
                            "min_value": 1,
                            "max_value": 20,
                        },
                    },
                    "derived": {},
                },
                "initial_attributes": {"level": 1},
                "resources": {},
            },
            revision=1,
        )

        session = make_session([
            unique_check_result(),  # check unique
            row_result(system),
            row_result(draft),
        ])

        result = await service.create_system_with_draft(session, GameSystemEditorCreate(
            system={
                "name": "Система с правилами",
                "slug": "with-rules",
                "description": None,
                "is_active": True,
                "rules_engine_version": "1.0",
            },
            rules={
                "schema_version": 4,
                "calculations": {
                    "attributes": {
                        "level": {
                            "label": "Уровень",
                            "min_value": 1,
                            "max_value": 20,
                        },
                    },
                    "derived": {},
                },
                "initial_attributes": {"level": 1},
                "resources": {},
            },
        ))

        self.assertIsInstance(result, GameSystemEditorRead)
        self.assertEqual(result.system.is_active, True)
        self.assertEqual(result.draft.rules.initial_attributes["level"], 1)


if __name__ == "__main__":
    unittest.main()
