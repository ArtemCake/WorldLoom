import json
import subprocess
from pathlib import Path

import pytest

from backend.app.modules.game_systems.rules.rules_engine import create_sheet_state, evaluate_sheet_state, validate_rules_profile
from backend.app.modules.game_systems.schemas.game_rules import RulesProfile, SheetStateChanges


@pytest.fixture(scope="module")
def dnd_profile():
	root = Path(__file__).resolve().parents[3]
	script = """
const module = await import('./frontend/src/js/features/game-systems/editor/presets/dnd5e-2014.js');
process.stdout.write(JSON.stringify(module.createDnd5e2014NumericProfile()));
"""
	command = ["node", "--input-type=module", "-e", script]
	result = subprocess.run(command, cwd=root, check=True, capture_output=True, text=True)
	profile = RulesProfile.model_validate(json.loads(result.stdout))

	return validate_rules_profile(profile)


def calculate(profile, **attributes):
	changes = SheetStateChanges(attributes=attributes) if attributes else None
	state = create_sheet_state(profile, changes=changes)

	return evaluate_sheet_state(profile, state).derived


def test_default_totals_preserve_existing_values(dnd_profile):
	result = calculate(dnd_profile)

	for code in dnd_profile.calculations.attributes:
		if not code.startswith("skill_") or not code.endswith("_rank"):
			continue

		skill = code[len("skill_"):-len("_rank")]

		assert result[f"skill_{skill}_total"] == result[f"skill_{skill}"]
		assert result[f"passive_{skill}_total"] == result[f"passive_{skill}_base"]

	for ability in ["strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"]:
		assert result[f"save_{ability}_total"] == result[f"save_{ability}"]

	assert result["initiative_total"] == result["initiative_base"]


def test_jack_applies_to_untrained_checks_and_initiative(dnd_profile):
	result = calculate(dnd_profile, level=5, jack_of_all_trades=1)

	assert result["proficiency_bonus"] == 3
	assert result["half_proficiency_floor"] == 1
	assert result["skill_arcana_total"] == 1
	assert result["check_intelligence_untrained_base"] == 1
	assert result["initiative_total"] == 1

	# Спасбросок не является проверкой характеристики.
	assert result["save_intelligence_total"] == 0


@pytest.mark.parametrize("rank, expected", [(0, 1), (1, 3), (2, 6)])
def test_jack_does_not_stack_with_skill_proficiency(dnd_profile, rank, expected):
	result = calculate(dnd_profile, level=5, jack_of_all_trades=1, skill_arcana_rank=rank)

	assert result["skill_arcana_total"] == expected


def test_remarkable_athlete_uses_rounding_up_without_stacking(dnd_profile):
	result = calculate(dnd_profile, level=13, jack_of_all_trades=1, remarkable_athlete=1)

	assert result["proficiency_bonus"] == 5
	assert result["half_proficiency_floor"] == 2
	assert result["half_proficiency_ceil"] == 3

	assert result["skill_athletics_total"] == 3
	assert result["skill_acrobatics_total"] == 3
	assert result["check_constitution_untrained_base"] == 3
	assert result["skill_arcana_total"] == 2
	assert result["initiative_total"] == 3
	assert result["save_constitution_total"] == 0


@pytest.mark.parametrize("rank, expected", [(1, 5), (2, 10)])
def test_athlete_does_not_add_half_to_trained_skill(dnd_profile, rank, expected):
	result = calculate(dnd_profile, level=13, remarkable_athlete=1, skill_athletics_rank=rank)

	assert result["skill_athletics_total"] == expected


@pytest.mark.parametrize("mode, expected", [(-1, 12), (0, 17), (1, 22)])
def test_passive_check_conditions(dnd_profile, mode, expected):
	attributes = {
		"level": 5,
		"wisdom": 14,
		"skill_perception_rank": 1,
		"skill_perception_bonus": 2,
		"passive_perception_mode": mode,
	}
	result = calculate(dnd_profile, **attributes)

	assert result["skill_perception_total"] == 7
	assert result["passive_perception_total"] == expected


def test_saving_throw_extra_bonus(dnd_profile):
	result = calculate(dnd_profile, wisdom=14, save_wisdom_trained=1, save_wisdom_bonus=4)

	assert result["save_wisdom"] == 4
	assert result["save_wisdom_total"] == 8


def test_initiative_proficiency_excludes_half_bonus(dnd_profile):
	attributes = {
		"level": 13,
		"dexterity": 14,
		"jack_of_all_trades": 1,
		"remarkable_athlete": 1,
		"initiative_trained": 1,
		"initiative_bonus": 4,
	}
	result = calculate(dnd_profile, **attributes)

	assert result["initiative_base"] == 2
	assert result["initiative_total"] == 11


def test_new_choice_fields_reject_unknown_values(dnd_profile):
	with pytest.raises(ValueError):
		calculate(dnd_profile, passive_perception_mode=2)

	with pytest.raises(ValueError):
		calculate(dnd_profile, jack_of_all_trades=2)
