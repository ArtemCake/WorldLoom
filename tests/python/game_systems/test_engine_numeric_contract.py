# tests/python/game_systems/test_engine_numeric_contract.py

"""Проверки числового контракта, используемого редактором движков."""

import unittest

from pydantic import ValidationError

from backend.app.modules.game_systems.rules.rules_engine import (
    create_sheet_state,
    evaluate_sheet_state,
    validate_rules_profile,
)
from backend.app.modules.game_systems.schemas.game_rules import RulesProfile


def make_profile():
    """Независимый профиль без обязательных характеристик готовой системы."""
    return {
        "schema_version": 3,
        "calculations": {
            "attributes": {
                "power": {
                    "label": "Мощь",
                    "min_value": 0,
                    "max_value": 30,
                },
            },
            "derived": {
                "modifier": {
                    "label": "Модификатор",
                    "formula": {
                        "operation": "floor_div",
                        "arguments": [
                            {
                                "operation": "subtract",
                                "arguments": ["attribute.power", 10],
                            },
                            2,
                        ],
                    },
                },
            },
        },
        "initial_attributes": {"power": 15},
    }


class EngineNumericContractTests(unittest.TestCase):
    def test_custom_attribute_can_be_calculated(self):
        profile = RulesProfile.model_validate(make_profile())
        validate_rules_profile(profile)

        state = create_sheet_state(profile)
        result = evaluate_sheet_state(profile, state)

        self.assertEqual(result.attributes, {"power": 15})
        self.assertEqual(result.derived, {"modifier": 2})

    def test_unknown_reference_is_rejected(self):
        raw = make_profile()
        raw["calculations"]["derived"]["modifier"]["formula"] = {
            "operation": "sum",
            "arguments": ["attribute.missing", 1],
        }

        with self.assertRaises(ValidationError):
            RulesProfile.model_validate(raw)

    def test_dependency_cycle_is_rejected(self):
        raw = make_profile()
        raw["calculations"]["derived"]["modifier"]["formula"] = {
            "operation": "sum",
            "arguments": ["stat.modifier"],
        }

        with self.assertRaises(ValidationError):
            RulesProfile.model_validate(raw)

    def test_old_format_is_not_relabelled_automatically(self):
        raw = make_profile()
        raw["schema_version"] = 2

        with self.assertRaises(ValidationError):
            RulesProfile.model_validate(raw)


if __name__ == "__main__":
    unittest.main()
