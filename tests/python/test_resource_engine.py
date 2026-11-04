# tests/python/test_resource_engine.py

import unittest

from pydantic import ValidationError

from backend.app.modules.game_systems.rules.resource_engine import (
    create_resource_state,
    recover_resources,
    resolve_resource_limits,
    restore_resources,
    spend_resources,
    validate_resource_state,
)

from backend.app.modules.game_systems.rules.rules_engine import (
    create_sheet_state,
)

from backend.app.modules.game_systems.schemas.game_rules import (
    RulesProfile,
    SheetState,
)

from backend.app.modules.game_systems.schemas.rules.rule_resources import (
    ResourceAmounts,
    ResourceDefinitions,
    ResourceState,
)


def make_profile():
    return RulesProfile.model_validate({
        "schema_version": 3,
        "calculations": {
            "attributes": {
                "level": {
                    "label": "Уровень",
                    "min_value": 1,
                    "max_value": 20,
                },
            },
            "derived": {
                "focus_max": {
                    "label": "Максимум сосредоточения",
                    "formula": {
                        "operation": "multiply",
                        "arguments": [
                            "attribute.level",
                            2,
                        ],
                    },
                },
            },
        },
        "initial_attributes": {
            "level": 3,
        },
    })


def make_definitions():
    # Это искусственный пример для тестов ядра,
    # а не классовые правила D&D.
    return ResourceDefinitions.model_validate({
        "resources": {
            "focus": {
                "label": "Сосредоточение",
                "maximum": "stat.focus_max",
                "initial": "full",
                "recovery": {
                    "short_rest": 2,
                    "long_rest": "full",
                },
            },
            "supplies": {
                "label": "Припасы",
                "maximum": 4,
                "initial": 1,
            },
        },
    })


class ResourceEngineTests(unittest.TestCase):
    def setUp(self):
        self.profile = make_profile()
        self.sheet = create_sheet_state(self.profile)
        self.definitions = make_definitions()

        self.state = create_resource_state(
            self.profile,
            self.sheet,
            self.definitions,
        )

    def spend(self, state, amounts):
        return spend_resources(
            self.profile,
            self.sheet,
            self.definitions,
            state,
            ResourceAmounts(amounts=amounts),
        )

    def test_maximum_uses_existing_numeric_calculation(self):
        limits = resolve_resource_limits(
            self.profile,
            self.sheet,
            self.definitions,
        )

        self.assertEqual(limits, {
            "focus": 6,
            "supplies": 4,
        })

    def test_initial_state(self):
        self.assertEqual(self.state.values, {
            "focus": 6,
            "supplies": 1,
        })

    def test_spend_returns_new_state(self):
        updated = self.spend(
            self.state,
            {"focus": 2},
        )

        self.assertEqual(updated.values["focus"], 4)
        self.assertEqual(self.state.values["focus"], 6)

    def test_insufficient_resource_does_not_change_input(self):
        before = self.state.model_dump()

        with self.assertRaises(ValueError):
            self.spend(
                self.state,
                {
                    "focus": 2,
                    "supplies": 2,
                },
            )

        self.assertEqual(
            self.state.model_dump(),
            before,
        )

    def test_exact_remaining_amount_can_be_spent(self):
        updated = self.spend(
            self.state,
            {"focus": 6},
        )

        self.assertEqual(updated.values["focus"], 0)

    def test_unknown_resource_is_rejected(self):
        with self.assertRaises(ValueError):
            self.spend(
                self.state,
                {"unknown": 1},
            )

    def test_invalid_amounts_are_rejected(self):
        for amount in [0, -1, True, 1.5, "2"]:
            with self.subTest(amount=amount):
                with self.assertRaises(ValidationError):
                    ResourceAmounts(
                        amounts={"focus": amount},
                    )

    def test_empty_amounts_are_rejected(self):
        with self.assertRaises(ValidationError):
            ResourceAmounts(amounts={})

    def test_restore_stops_at_maximum(self):
        spent = self.spend(
            self.state,
            {"focus": 5},
        )

        restored = restore_resources(
            self.profile,
            self.sheet,
            self.definitions,
            spent,
            ResourceAmounts(
                amounts={"focus": 20},
            ),
        )

        self.assertEqual(restored.values["focus"], 6)
        self.assertEqual(spent.values["focus"], 1)

    def test_partial_recovery_event(self):
        spent = self.spend(
            self.state,
            {"focus": 5},
        )

        restored = recover_resources(
            self.profile,
            self.sheet,
            self.definitions,
            spent,
            "short_rest",
        )

        self.assertEqual(restored.values["focus"], 3)
        self.assertEqual(restored.values["supplies"], 1)
        self.assertEqual(spent.values["focus"], 1)

    def test_full_recovery_event(self):
        spent = self.spend(
            self.state,
            {"focus": 5},
        )

        restored = recover_resources(
            self.profile,
            self.sheet,
            self.definitions,
            spent,
            "long_rest",
        )

        self.assertEqual(restored.values["focus"], 6)

        # Без явно заданного правила припасы
        # от отдыха не восстанавливаются.
        self.assertEqual(restored.values["supplies"], 1)

    def test_unconfigured_event_does_not_restore_anything(self):
        spent = self.spend(
            self.state,
            {"focus": 3},
        )

        restored = recover_resources(
            self.profile,
            self.sheet,
            self.definitions,
            spent,
            "dawn",
        )

        self.assertEqual(
            restored.model_dump(),
            spent.model_dump(),
        )

        self.assertIsNot(restored, spent)

    def test_missing_resource_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_resource_state(
                self.profile,
                self.sheet,
                self.definitions,
                ResourceState(values={"focus": 6}),
            )

    def test_extra_resource_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_resource_state(
                self.profile,
                self.sheet,
                self.definitions,
                ResourceState(values={
                    "focus": 6,
                    "supplies": 1,
                    "unknown": 0,
                }),
            )

    def test_current_value_above_maximum_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_resource_state(
                self.profile,
                self.sheet,
                self.definitions,
                ResourceState(values={
                    "focus": 7,
                    "supplies": 1,
                }),
            )

    def test_negative_current_value_is_rejected(self):
        with self.assertRaises(ValidationError):
            ResourceState(values={"focus": -1})

    def test_initial_above_computed_maximum_is_rejected(self):
        definitions = ResourceDefinitions.model_validate({
            "resources": {
                "focus": {
                    "label": "Сосредоточение",
                    "maximum": "stat.focus_max",
                    "initial": 7,
                },
            },
        })

        with self.assertRaises(ValueError):
            create_resource_state(
                self.profile,
                self.sheet,
                definitions,
            )

    def test_unknown_maximum_reference_is_rejected(self):
        definitions = ResourceDefinitions.model_validate({
            "resources": {
                "focus": {
                    "label": "Сосредоточение",
                    "maximum": "stat.missing",
                },
            },
        })

        with self.assertRaises(ValueError):
            create_resource_state(
                self.profile,
                self.sheet,
                definitions,
            )

    def test_negative_computed_maximum_is_rejected(self):
        raw = self.profile.model_dump()
        raw["calculations"]["derived"]["focus_max"]["formula"] = {
            "operation": "subtract",
            "arguments": [0, "attribute.level"],
        }

        profile = RulesProfile.model_validate(raw)

        with self.assertRaises(ValueError):
            create_resource_state(
                profile,
                self.sheet,
                self.definitions,
            )

    def test_maximum_decrease_requires_explicit_resolution(self):
        lower_level = SheetState(
            attributes={"level": 1},
        )

        before = self.state.model_dump()

        with self.assertRaises(ValueError):
            validate_resource_state(
                self.profile,
                lower_level,
                self.definitions,
                self.state,
            )

        self.assertEqual(
            self.state.model_dump(),
            before,
        )

    def test_zero_capacity_is_allowed(self):
        definitions = ResourceDefinitions.model_validate({
            "resources": {
                "inactive": {
                    "label": "Недоступный ресурс",
                    "maximum": 0,
                },
            },
        })

        state = create_resource_state(
            self.profile,
            self.sheet,
            definitions,
        )

        self.assertEqual(
            state.values,
            {"inactive": 0},
        )

    def test_attribute_reference_is_supported(self):
        definitions = ResourceDefinitions.model_validate({
            "resources": {
                "points": {
                    "label": "Очки",
                    "maximum": "attribute.level",
                },
            },
        })

        state = create_resource_state(
            self.profile,
            self.sheet,
            definitions,
        )

        self.assertEqual(
            state.values,
            {"points": 3},
        )

    def test_definitions_and_state_survive_json(self):
        definitions = ResourceDefinitions.model_validate_json(
            self.definitions.model_dump_json()
        )

        state = ResourceState.model_validate_json(
            self.state.model_dump_json()
        )

        self.assertEqual(
            definitions.model_dump(),
            self.definitions.model_dump(),
        )

        self.assertEqual(
            state.model_dump(),
            self.state.model_dump(),
        )

        validated = validate_resource_state(
            self.profile,
            self.sheet,
            definitions,
            state,
        )

        self.assertEqual(
            validated.model_dump(),
            state.model_dump(),
        )


if __name__ == "__main__":
    unittest.main()
