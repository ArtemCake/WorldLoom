import asyncio

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from backend.app.modules.game_systems.errors import GameSystemRulesConflict, InvalidGameSystemRules
from backend.app.modules.game_systems.rules.rules_composition import compose_system_draft, compose_system_rules
from backend.app.modules.game_systems.schemas.game_rules import GameSystemRulesPublish, RulesProfile
from backend.app.modules.game_systems.services import editor_service, system_rule_origin


def profile_data(divisor: int = 0) -> dict:
    return {
        "schema_version": 4,
        "calculations": {
            "attributes": {
                "divisor": {
                    "label": "Делитель",
                    "field_type": "integer",
                    "min_value": 0,
                    "max_value": 10,
                },
            },
            "derived": {
                "result": {
                    "label": "Результат",
                    "short_label": "Рез",
                    "formula": {
                        "operation": "floor_div",
                        "arguments": [10, "attribute.divisor"],
                    },
                },
            },
        },
        "initial_attributes": {"divisor": divisor},
        "resources": {},
    }


def published_base() -> dict:
    return {
        "id": uuid4(),
        "rules_engine_version": "1.0",
        "rules_json": profile_data(2),
    }


def test_standalone_draft_does_not_execute_initial_formulas():
    raw = profile_data()
    before = deepcopy(raw)
    profile = RulesProfile.model_validate(raw)

    payload = editor_service._incoming_payload(profile)

    assert payload["initial_attributes"]["divisor"] == 0
    assert payload["calculations"]["derived"]["result"]["short_label"] == "Рез"
    assert raw == before

    with pytest.raises(ValueError):
        editor_service._rules_payload(payload)


def test_invalid_initial_value_is_still_rejected():
    raw = profile_data()
    raw["initial_attributes"]["divisor"] = 11

    with pytest.raises(ValueError):
        RulesProfile.model_validate(raw)


def test_incomplete_formula_is_still_rejected():
    raw = profile_data()
    raw["calculations"]["derived"]["result"]["formula"]["arguments"] = [10]

    with pytest.raises(ValueError):
        RulesProfile.model_validate(raw)


def test_missing_reference_is_still_rejected():
    raw = profile_data()
    formula = raw["calculations"]["derived"]["result"]["formula"]
    formula["arguments"] = [10, "attribute.missing"]

    with pytest.raises(ValueError):
        RulesProfile.model_validate(raw)


def test_draft_composition_does_not_modify_base_or_overrides():
    base = RulesProfile.model_validate(profile_data(2))
    original = base.model_dump(mode="python")
    overrides = {"initial_attributes": {"divisor": 0}}
    before = deepcopy(overrides)

    draft = compose_system_draft(base, overrides)

    assert draft.initial_attributes["divisor"] == 0
    assert base.model_dump(mode="python") == original
    assert overrides == before

    with pytest.raises(ValueError):
        compose_system_rules(base, overrides)


def test_unknown_override_section_is_still_rejected():
    base = RulesProfile.model_validate(profile_data(2))

    with pytest.raises(ValueError, match="Недопустимые разделы"):
        compose_system_draft(base, {"schema_version": 3})


def test_linked_draft_can_be_assembled_without_execution():
    version = published_base()
    before = deepcopy(version)
    overrides = {"initial_attributes": {"divisor": 0}}

    result = system_rule_origin._assemble(
        version,
        overrides,
        "1.0",
        stored=False,
        draft_mode=True,
    )

    assert result["engine_version_id"] == version["id"]
    assert result["rules_json"]["initial_attributes"]["divisor"] == 0
    assert result["rules_overrides_json"] == overrides
    assert version == before


def test_strict_origin_assembly_still_rejects_nonexecutable_rules():
    version = published_base()
    overrides = {"initial_attributes": {"divisor": 0}}

    with pytest.raises(InvalidGameSystemRules):
        system_rule_origin._assemble(version, overrides, "1.0", stored=False)

    with pytest.raises(GameSystemRulesConflict):
        system_rule_origin._assemble(version, overrides, "1.0", stored=True)


def test_invalid_published_base_is_not_accepted_even_for_draft():
    version = published_base()
    version["rules_json"] = profile_data(0)

    with pytest.raises(GameSystemRulesConflict):
        system_rule_origin._assemble(
            version,
            {"initial_attributes": {"divisor": 2}},
            "1.0",
            stored=False,
            draft_mode=True,
        )


def test_corrected_initial_value_passes_strict_validation():
    base = RulesProfile.model_validate(profile_data(2))
    profile = compose_system_rules(base, {"initial_attributes": {"divisor": 5}})

    payload = editor_service._rules_payload(profile)

    assert payload["initial_attributes"]["divisor"] == 5


def test_publication_rejects_nonexecutable_draft_before_database_write(monkeypatch):
    session = SimpleNamespace(
        new=(),
        dirty=(),
        deleted=(),
        execute=AsyncMock(),
    )

    system = {
        "is_active": True,
        "rules_engine_version": "1.0",
    }

    draft = {
        "revision": 3,
        "rules_json": profile_data(0),
        "engine_version_id": None,
        "rules_overrides_json": None,
    }

    monkeypatch.setattr(editor_service, "_get_system", AsyncMock(return_value=system))
    monkeypatch.setattr(editor_service, "_find_draft", AsyncMock(return_value=draft))

    data = GameSystemRulesPublish(expected_revision=3)

    with pytest.raises(GameSystemRulesConflict):
        asyncio.run(editor_service.publish_rules_version(session, uuid4(), data))

    session.execute.assert_not_awaited()
    assert draft["revision"] == 3
