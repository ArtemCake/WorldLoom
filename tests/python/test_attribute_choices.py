import copy
import unittest

from pydantic import ValidationError

from backend.app.modules.game_systems.rules.rules_engine import (
    apply_sheet_changes,
    create_sheet_state,
    evaluate_sheet_state,
    validate_rules_profile,
)
from backend.app.modules.game_systems.schemas.game_rules import (
    RulesProfile,
    SheetState,
    SheetStateChanges,
)
from backend.app.modules.game_systems.schemas.rule_calculations import (
    AttributeDefinition,
    AttributePreviewInput,
)


def raw_profile():
    # Намеренно непоследовательные варианты:
    # диапазон 0..2 не должен разрешать значение 1.
    return {
        "schema_version": 3,
        "calculations": {
            "attributes": {
                "rank": {
                    "label": "Владение",
                    "field_type": "choice",
                    "choices": [
                        {"value": 0, "label": "Нет владения"},
                        {"value": 2, "label": "Удвоение"},
                    ],
                    "min_value": 0,
                    "max_value": 2,
                }
            },
            "derived": {
                "bonus": {
                    "label": "Бонус",
                    "formula": {
                        "operation": "multiply",
                        "arguments": [
                            "attribute.rank",
                            3,
                        ],
                    },
                }
            },
        },
        "initial_attributes": {"rank": 0},
    }


class AttributeChoicesTests(unittest.TestCase):
    def profile(self):
        return validate_rules_profile(
            RulesProfile.model_validate(raw_profile())
        )

    def test_old_numeric_definition_remains_valid(self):
        definition = AttributeDefinition.model_validate({
            "label": "Сила",
            "min_value": 0,
            "max_value": 30,
        })

        self.assertEqual(definition.field_type, "integer")
        self.assertEqual(definition.validate_value(10), 10)

    def test_choice_metadata_survives_json(self):
        profile = self.profile()

        restored = RulesProfile.model_validate_json(
            profile.model_dump_json()
        )

        self.assertEqual(
            profile.model_dump(mode="json"),
            restored.model_dump(mode="json"),
        )

        choice = restored.calculations.attributes["rank"].choices[1]
        self.assertEqual(choice.label, "Удвоение")
        self.assertEqual(choice.value, 2)

    def test_allowed_choice_is_used_in_formula(self):
        profile = self.profile()

        state = create_sheet_state(
            profile,
            SheetStateChanges(attributes={"rank": 2}),
        )

        result = evaluate_sheet_state(profile, state)
        self.assertEqual(result.derived["bonus"], 6)

    def test_initial_value_must_belong_to_choices(self):
        raw = raw_profile()
        raw["initial_attributes"]["rank"] = 1

        with self.assertRaises(ValidationError):
            RulesProfile.model_validate(raw)

    def test_preview_rejects_value_between_choices(self):
        profile = self.profile()

        with self.assertRaises(ValidationError):
            AttributePreviewInput(
                calculations=profile.calculations,
                attributes={"rank": 1},
            )

    def test_create_state_rejects_invalid_choice(self):
        with self.assertRaises(ValueError):
            create_sheet_state(
                self.profile(),
                SheetStateChanges(attributes={"rank": 1}),
            )

    def test_apply_rejects_choice_without_mutating_state(self):
        profile = self.profile()
        state = create_sheet_state(profile)
        before = copy.deepcopy(state.model_dump())

        with self.assertRaises(ValueError):
            apply_sheet_changes(
                profile,
                state,
                SheetStateChanges(attributes={"rank": 1}),
            )

        self.assertEqual(state.model_dump(), before)

    def test_evaluation_rejects_invalid_existing_state(self):
        with self.assertRaises(ValueError):
            evaluate_sheet_state(
                self.profile(),
                SheetState(attributes={"rank": 1}),
            )

    def test_duplicate_values_are_rejected(self):
        raw = raw_profile()
        raw["calculations"]["attributes"]["rank"]["choices"][1]["value"] = 0

        with self.assertRaises(ValidationError):
            RulesProfile.model_validate(raw)

    def test_empty_choices_are_rejected(self):
        raw = raw_profile()
        raw["calculations"]["attributes"]["rank"]["choices"] = []

        with self.assertRaises(ValidationError):
            RulesProfile.model_validate(raw)

    def test_numeric_field_cannot_have_choices(self):
        raw = raw_profile()
        raw["calculations"]["attributes"]["rank"]["field_type"] = "integer"

        with self.assertRaises(ValidationError):
            RulesProfile.model_validate(raw)

    def test_boolean_is_not_a_choice_number(self):
        raw = raw_profile()
        raw["calculations"]["attributes"]["rank"]["choices"][0]["value"] = False

        with self.assertRaises(ValidationError):
            RulesProfile.model_validate(raw)


if __name__ == "__main__":
    unittest.main()