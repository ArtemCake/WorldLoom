# tests/python/game_systems/test_engine_resource_storage.py

import unittest

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from backend.app.modules.game_systems.errors import GameSystemRulesConflict
from backend.app.modules.game_systems.schemas.game_rules import RulesProfile
from backend.app.modules.game_systems.schemas.rules.rule_engines import RuleEngineCreate, RuleEngineDraftUpdate, RuleEnginePublish
from backend.app.modules.game_systems.services import rule_engine_service as service


def make_profile(version: int = 4) -> RulesProfile:
    raw = {
        "schema_version": version,
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
        "initial_attributes": {"level": 3},
    }

    if version == 4:
        raw["resources"] = {
            "points": {
                "label": "Очки",
                "maximum": "attribute.level",
                "initial": "full",
                "recovery": {"long_rest": "full"},
            },
        }

    return RulesProfile.model_validate(raw)


def row_result(row: dict):
    result = MagicMock()
    result.mappings.return_value.one.return_value = row
    result.mappings.return_value.one_or_none.return_value = row

    return result


def scalar_result(value: int):
    result = MagicMock()
    result.scalar_one.return_value = value
    result.scalar_one_or_none.return_value = value

    return result


def make_session(results: list):
    return SimpleNamespace(new=(), dirty=(), deleted=(), execute=AsyncMock(side_effect=results))


class EngineResourceStorageTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.actor_id = uuid4()
        self.engine_id = uuid4()
        self.now = datetime.now(timezone.utc)
        self.profile = make_profile()
        self.payload = self.profile.model_dump(mode="json")

        self.engine = {
            "id": self.engine_id,
            "owner_id": self.actor_id,
            "name": "Тестовая игровая система",
            "slug": "resource-storage-test",
            "description": None,
            "visibility": "private",
            "is_active": True,
            "created_at": self.now,
            "updated_at": self.now,
        }

        self.draft = {
            "id": uuid4(),
            "engine_id": self.engine_id,
            "rules_json": self.payload,
            "rules_engine_version": "1.0",
            "revision": 1,
            "created_at": self.now,
            "updated_at": self.now,
        }

    def assert_written_payload(self, session, statement_index: int):
        statement = session.execute.await_args_list[statement_index].args[0]
        written = statement.compile().params["rules_json"]
        restored = RulesProfile.model_validate(written)

        self.assertEqual(restored.schema_version, 4)
        self.assertEqual(restored.resources, self.profile.resources)

    async def test_create_writes_resources_and_returns_them(self):
        session = make_session([row_result(self.engine), row_result(self.draft)])

        data = RuleEngineCreate(name="Тестовая игровая система", slug="resource-storage-test", rules=self.profile)

        response = await service.create_engine_with_draft(session, self.actor_id, data)

        self.assert_written_payload(session, 1)
        self.assertEqual(response.draft.rules_json.resources, self.profile.resources)

    async def test_update_writes_resources_and_returns_them(self):
        saved = dict(self.draft)
        saved["revision"] = 2

        results = [row_result(self.engine), row_result(self.draft), row_result(saved)]
        session = make_session(results)
        data = RuleEngineDraftUpdate(rules=self.profile, expected_revision=1)

        response = await service.update_engine_draft(session, self.engine_id, self.actor_id, data)

        self.assert_written_payload(session, 2)
        self.assertEqual(response.rules_json.resources, self.profile.resources)
        self.assertEqual(response.revision, 2)

    async def test_publish_writes_resources_and_returns_them(self):
        version = {
            "id": uuid4(),
            "engine_id": self.engine_id,
            "version_number": 1,
            "source_draft_revision": 1,
            "rules_json": self.payload,
            "rules_engine_version": "1.0",
            "published_at": self.now,
        }

        results = [
            row_result(self.engine),
            row_result(self.draft),
            scalar_result(1),
            row_result(version),
            scalar_result(2),
        ]

        session = make_session(results)
        data = RuleEnginePublish(expected_revision=1)

        response = await service.publish_engine_version(session, self.engine_id, self.actor_id, data)

        self.assert_written_payload(session, 3)
        self.assertEqual(response.rules_json.resources, self.profile.resources)

    async def test_old_editor_cannot_downgrade_profile(self):
        session = make_session([row_result(self.engine), row_result(self.draft)])
        data = RuleEngineDraftUpdate(rules=make_profile(3), expected_revision=1)

        with self.assertRaises(GameSystemRulesConflict):
            await service.update_engine_draft(session, self.engine_id, self.actor_id, data)

        self.assertEqual(session.execute.await_count, 2)

    def test_explicit_upgrade_is_allowed(self):
        current = make_profile(3).model_dump(mode="json")

        service._check_profile_replacement(current, self.payload)

    def test_invalid_resource_profile_is_rejected_before_storage(self):
        raw = self.profile.model_dump(mode="json")
        raw["resources"]["points"]["initial"] = 4

        with self.assertRaises(ValueError):
            service._payload(raw)


if __name__ == "__main__":
    unittest.main()
