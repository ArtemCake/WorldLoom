import json
import subprocess
from pathlib import Path

import pytest

from backend.app.modules.game_systems.rules.rules_engine import create_sheet_state, evaluate_sheet_state
from backend.app.modules.game_systems.rules.rules_engine import validate_rules_profile
from backend.app.modules.game_systems.schemas.game_rules import RulesProfile, SheetStateChanges


@pytest.fixture(scope="module")
def extended_profile():
	root = Path(__file__).resolve().parents[3]
	script = """
const path = './frontend/src/js/features/game-systems/editor/presets/dnd5e-2014.js';
const module = await import(path);
process.stdout.write(JSON.stringify(module.createDnd5e2014NumericProfile()));
"""
	command = ["node", "--input-type=module", "-e", script]
	result = subprocess.run(
		command,
		cwd=root,
		check=True,
		capture_output=True,
		text=True,
		encoding="utf-8",
	)
	profile = RulesProfile.model_validate(json.loads(result.stdout))

	return validate_rules_profile(profile)


def calculate(profile, **attributes):
	changes = SheetStateChanges(attributes=attributes) if attributes else None
	state = create_sheet_state(profile, changes=changes)

	return evaluate_sheet_state(profile, state).derived


def test_default_profile_evaluates(extended_profile):
	values = calculate(extended_profile)

	assert values["proficiency_bonus"] == 2
	assert values["armor_class_total"] == 10
	assert values["pact_slots_max"] == 0
	assert values["spell_slots_1_max"] == 0


@pytest.mark.parametrize("tier, expected", [(1, 4), (2, 3), (3, 2), (4, 0), (9, 0)])
def test_full_caster_fifth_level_slots(extended_profile, tier, expected):
	values = calculate(extended_profile, spell_slot_table_level=5)

	assert values[f"spell_slots_{tier}_max"] == expected


def test_full_caster_twentieth_level_slots(extended_profile):
	values = calculate(extended_profile, spell_slot_table_level=20)
	slots = [values[f"spell_slots_{tier}_max"] for tier in range(1, 10)]

	assert slots == [4, 3, 3, 3, 3, 2, 2, 1, 1]


@pytest.mark.parametrize("level, count, tier", [(1, 1, 1), (3, 2, 2), (11, 3, 5), (17, 4, 5), (20, 4, 5)])
def test_pact_magic(extended_profile, level, count, tier):
	values = calculate(extended_profile, class_warlock_level=level)

	assert values["pact_slots_max"] == count
	assert values["pact_slot_level"] == tier


def test_multiclass_hit_dice_pools(extended_profile):
	values = calculate(extended_profile, level=8, class_fighter_level=5, class_wizard_level=3)

	assert values["class_levels_total"] == 8
	assert values["class_level_gap"] == 0
	assert values["hit_dice_d10_max"] == 5
	assert values["hit_dice_d6_max"] == 3
	assert values["hit_dice_rest_budget"] == 4


def test_hit_dice_do_not_all_recover_on_long_rest(extended_profile):
	for die in [6, 8, 10, 12]:
		assert extended_profile.resources[f"hit_dice_d{die}"].recovery == {}


@pytest.mark.parametrize("dexterity, expected", [(8, 17), (18, 17)])
def test_heavy_armor_ignores_dexterity(extended_profile, dexterity, expected):
	values = calculate(extended_profile, armor_type=11, dexterity=dexterity)

	assert values["armor_class_total"] == expected


def test_medium_armor_caps_dexterity(extended_profile):
	values = calculate(extended_profile, armor_type=8, dexterity=18, shield_equipped=1)

	assert values["armor_class_total"] == 19


def test_medium_armor_keeps_negative_dexterity(extended_profile):
	values = calculate(extended_profile, armor_type=8, dexterity=8)

	assert values["armor_class_total"] == 14


def test_barbarian_armor_method_with_shield(extended_profile):
	values = calculate(extended_profile, armor_class_method=1, dexterity=14, constitution=16, shield_equipped=1)

	assert values["armor_class_total"] == 17


def test_money_and_coin_weight(extended_profile):
	values = calculate(extended_profile, coins_gold=50)

	assert values["money_copper_total"] == 5000
	assert values["coin_count_total"] == 50
	assert values["carried_weight_hundredths"] == 100


def test_medium_creature_capacity(extended_profile):
	values = calculate(extended_profile, strength=10)

	assert values["carrying_capacity_hundredths"] == 15000
	assert values["push_drag_lift_hundredths"] == 30000


def test_tiny_creature_capacity_keeps_fractional_pounds(extended_profile):
	values = calculate(extended_profile, strength=1, capacity_size_halves=1)

	assert values["carrying_capacity_hundredths"] == 750


@pytest.mark.parametrize("damage, expected", [(0, 10), (21, 10), (22, 11), (40, 20)])
def test_concentration_dc(extended_profile, damage, expected):
	values = calculate(extended_profile, concentration_damage=damage)

	assert values["concentration_dc"] == expected


def test_spellcasting_ability(extended_profile):
	values = calculate(extended_profile, level=5, intelligence=16)

	assert values["spell_intelligence_attack"] == 6
	assert values["spell_intelligence_dc"] == 14


def test_rulebook_and_sections_are_present(extended_profile):
	assert extended_profile.rulebook["networks"].status == "unused"
	assert extended_profile.rulebook["rest"].fields["restoration"]

	for definition in extended_profile.calculations.attributes.values():
		assert definition.section

	for definition in extended_profile.calculations.derived.values():
		assert definition.section

	for definition in extended_profile.resources.values():
		assert definition.section


def test_original_codes_are_preserved(extended_profile):
	values = calculate(extended_profile)

	for code in ["skill_perception", "passive_perception_base", "initiative_base", "save_wisdom"]:
		assert code in values

	assert "hit_points_max" in extended_profile.calculations.attributes
	assert "hit_points" in extended_profile.resources
