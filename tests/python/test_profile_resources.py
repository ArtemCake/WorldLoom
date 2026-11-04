# tests/python/test_profile_resources.py

import unittest

from pydantic import ValidationError

from backend.app.modules.game_systems.rules.resource_engine import spend_resources
from backend.app.modules.game_systems.rules.rules_composition import compose_system_rules
from backend.app.modules.game_systems.rules.rules_engine import validate_rules_profile
from backend.app.modules.game_systems.schemas.game_rules import RulesProfile, SheetState
from backend.app.modules.game_systems.schemas.rules.rule_resources import ResourceAmounts, ResourceDefinitions, ResourceState


def make_raw_profile(version: int = 4) -> dict:
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
            "derived": {
                "points_max": {
                    "label": "Максимум очков",
                    "formula": {
                        "operation": "multiply",
                        "arguments": ["attribute.level", 2],
                    },
                },
            },
        },
        "initial_attributes": {"level": 3},
    }

    if version == 4:
        raw["resources"] = {
            "points": {
                "label": "Очки",
                "maximum": "stat.points_max",
                "initial": "full",
                "recovery": {"long_rest": "full"},
            },
        }

    return raw


class ProfileResourcesTests(unittest.TestCase):
    def make_profile(self) -> RulesProfile:
        return validate_rules_profile(RulesProfile.model_validate(make_raw_profile()))

    def test_version_three_without_resources_remains_valid(self):
        profile = RulesProfile.model_validate(make_raw_profile(3))
        validate_rules_profile(profile)

        self.assertEqual(profile.schema_version, 3)
        self.assertEqual(profile.resources, {})

        restored = RulesProfile.model_validate_json(profile.model_dump_json())

        self.assertEqual(restored.schema_version, 3)
        self.assertEqual(restored.resources, {})

    def test_version_three_cannot_contain_resources(self):
        raw = make_raw_profile()
        raw["schema_version"] = 3

        with self.assertRaises(ValidationError):
            RulesProfile.model_validate(raw)

    def test_version_four_requires_explicit_resources_section(self):
        raw = make_raw_profile()
        del raw["resources"]

        with self.assertRaises(ValidationError):
            RulesProfile.model_validate(raw)

    def test_version_four_allows_explicit_empty_resources(self):
        raw = make_raw_profile()
        raw["resources"] = {}

        profile = validate_rules_profile(RulesProfile.model_validate(raw))

        self.assertEqual(profile.resources, {})

    def test_resources_survive_json_round_trip(self):
        profile = self.make_profile()
        restored = RulesProfile.model_validate_json(profile.model_dump_json())

        validate_rules_profile(restored)

        self.assertEqual(restored.model_dump(), profile.model_dump())
        self.assertEqual(restored.resources["points"].maximum, "stat.points_max")
        self.assertEqual(restored.resources["points"].recovery, {"long_rest": "full"})

    def test_unknown_maximum_reference_is_rejected(self):
        raw = make_raw_profile()
        raw["resources"]["points"]["maximum"] = "stat.missing"

        with self.assertRaises(ValidationError):
            RulesProfile.model_validate(raw)

    def test_reference_namespace_is_significant(self):
        raw = make_raw_profile()
        raw["resources"]["points"]["maximum"] = "attribute.points_max"

        with self.assertRaises(ValidationError):
            RulesProfile.model_validate(raw)

    def test_negative_computed_maximum_is_rejected(self):
        raw = make_raw_profile()
        raw["calculations"]["derived"]["points_max"]["formula"] = {
            "operation": "subtract",
            "arguments": [0, "attribute.level"],
        }

        profile = RulesProfile.model_validate(raw)

        with self.assertRaises(ValueError):
            validate_rules_profile(profile)

    def test_initial_above_computed_maximum_is_rejected(self):
        raw = make_raw_profile()
        raw["resources"]["points"]["initial"] = 7

        profile = RulesProfile.model_validate(raw)

        with self.assertRaises(ValueError):
            validate_rules_profile(profile)

    def test_composition_inherits_resources(self):
        base = self.make_profile()
        effective = compose_system_rules(base)

        self.assertEqual(effective.resources, base.resources)
        self.assertIsNot(effective.resources, base.resources)

    def test_composition_can_explicitly_remove_resources(self):
        base = self.make_profile()
        effective = compose_system_rules(base, {"resources": {}})

        self.assertEqual(effective.resources, {})
        self.assertIn("points", base.resources)

    def test_composition_replaces_whole_resource_section(self):
        base = self.make_profile()
        replacement = {
            "other": {
                "label": "Другой ресурс",
                "maximum": 4,
                "initial": 1,
            },
        }

        effective = compose_system_rules(base, {"resources": replacement})

        self.assertEqual(set(effective.resources), {"other"})
        self.assertEqual(set(base.resources), {"points"})

        replacement["other"]["label"] = "Изменено снаружи"

        self.assertEqual(effective.resources["other"].label, "Другой ресурс")

    def test_composition_rechecks_resource_limits_after_numeric_override(self):
        raw = make_raw_profile()
        raw["resources"]["points"]["initial"] = 5

        base = validate_rules_profile(RulesProfile.model_validate(raw))
        overrides = {"initial_attributes": {"level": 1}}

        with self.assertRaises(ValueError):
            compose_system_rules(base, overrides)

    def test_null_resources_are_rejected(self):
        with self.assertRaises(ValidationError):
            compose_system_rules(self.make_profile(), {"resources": None})

    def test_existing_resource_does_not_reapply_initial_fill(self):
        raw = make_raw_profile()
        raw["resources"]["points"]["initial"] = 5

        profile = validate_rules_profile(RulesProfile.model_validate(raw))
        definitions = ResourceDefinitions(resources=profile.resources)

        sheet = SheetState(attributes={"level": 1})
        state = ResourceState(values={"points": 2})
        amounts = ResourceAmounts(amounts={"points": 1})

        updated = spend_resources(profile, sheet, definitions, state, amounts)

        self.assertEqual(updated.values["points"], 1)
        self.assertEqual(state.values["points"], 2)


if __name__ == "__main__":
    unittest.main()
