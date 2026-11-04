# tests/python/test_dnd5e_2014_preset.py

"""Проверка JS-пресета D&D 2014 серверным числовым исполнителем.

Требует Node.js в PATH.

Проверяет:
- загрузку фактического пресета из frontend;
- принятие серверным контрактом;
- сохранность при JSON-сериализации;
- расчёты серверным исполнителем.

Не проверяет браузерный DOM, HTTP-маршруты и запись в БД.
"""

import copy
import json
from pathlib import Path
import shutil
import subprocess
import unittest

from backend.app.modules.game_systems.rules.rules_engine import (
    create_sheet_state,
    evaluate_sheet_state,
    validate_rules_profile,
)
from backend.app.modules.game_systems.schemas.game_rules import (
    RulesProfile,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

PRESET_EXPORT_SCRIPT = """
import {
    createEnginePreset
} from './frontend/src/js/features/game-systems/editor/engine-presets.js';

process.stdout.write(
    JSON.stringify(createEnginePreset('dnd5e_2014_srd51'))
);
"""


class Dnd5e2014PresetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        node = shutil.which("node")

        if node is None:
            raise RuntimeError(
                "Для проверки JS-пресета нужен Node.js в PATH."
            )

        completed = subprocess.run(
            [
                node,
                "--input-type=module",
                "--eval",
                PRESET_EXPORT_SCRIPT,
            ],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            encoding="utf-8",
            timeout=30,
        )

        cls.raw_profile = json.loads(completed.stdout)

    def make_profile(self, attributes=None):
        raw = copy.deepcopy(self.raw_profile)

        if attributes:
            raw["initial_attributes"].update(attributes)

        profile = RulesProfile.model_validate(raw)
        return validate_rules_profile(profile)

    def evaluate(self, attributes=None):
        profile = self.make_profile(attributes)
        state = create_sheet_state(profile)
        return evaluate_sheet_state(profile, state)

    def test_actual_js_preset_is_accepted(self):
        profile = self.make_profile()

        self.assertEqual(profile.schema_version, 3)
        self.assertEqual(
            len(profile.calculations.attributes),
            31,
        )
        self.assertEqual(
            len(profile.calculations.derived),
            51,
        )

    def test_profile_survives_json_round_trip(self):
        profile = self.make_profile()

        restored = RulesProfile.model_validate_json(
            profile.model_dump_json()
        )

        validate_rules_profile(restored)

        self.assertEqual(
            restored.model_dump(mode="json"),
            profile.model_dump(mode="json"),
        )

        before = evaluate_sheet_state(
            profile,
            create_sheet_state(profile),
        )

        after = evaluate_sheet_state(
            restored,
            create_sheet_state(restored),
        )

        self.assertEqual(before.attributes, after.attributes)
        self.assertEqual(before.derived, after.derived)

    def test_negative_modifier_uses_floor_rounding(self):
        result = self.evaluate({"strength": 9})

        self.assertEqual(
            result.derived["strength_modifier"],
            -1,
        )

    def test_proficiency_progression(self):
        cases = [
            (1, 2),
            (5, 3),
            (9, 4),
            (13, 5),
            (17, 6),
            (20, 6),
        ]

        for level, expected in cases:
            with self.subTest(level=level):
                result = self.evaluate({"level": level})

                self.assertEqual(
                    result.derived["proficiency_bonus"],
                    expected,
                )

    def test_skill_proficiency_and_expertise(self):
        for rank, expected in [(0, 3), (1, 6), (2, 9)]:
            with self.subTest(rank=rank):
                result = self.evaluate({
                    "dexterity": 16,
                    "level": 5,
                    "skill_stealth_rank": rank,
                })

                self.assertEqual(
                    result.derived["skill_stealth"],
                    expected,
                )

                self.assertEqual(
                    result.derived["passive_stealth_base"],
                    10 + expected,
                    )

    def test_saving_throw(self):
        result = self.evaluate({
            "dexterity": 16,
            "level": 5,
            "save_dexterity_trained": 1,
        })

        self.assertEqual(
            result.derived["save_dexterity"],
            6,
        )

    def test_passive_perception(self):
        result = self.evaluate({
            "wisdom": 15,
            "level": 1,
            "skill_perception_rank": 1,
        })

        self.assertEqual(
            result.derived["passive_perception_base"],
            14,
        )

    def test_edited_formula_survives_serialization(self):
        raw = copy.deepcopy(self.raw_profile)
        raw["initial_attributes"]["dexterity"] = 16

        raw["calculations"]["derived"]["initiative_base"]["formula"] = {
            "operation": "sum",
            "arguments": [
                "stat.dexterity_modifier",
                2,
            ],
        }

        profile = RulesProfile.model_validate(raw)
        validate_rules_profile(profile)

        restored = RulesProfile.model_validate_json(
            profile.model_dump_json()
        )
        validate_rules_profile(restored)

        result = evaluate_sheet_state(
            restored,
            create_sheet_state(restored),
        )

        self.assertEqual(
            result.derived["initiative_base"],
            5,
        )


if __name__ == "__main__":
    unittest.main()