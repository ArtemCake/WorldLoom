# tests/python/game_systems/test_effect_stacking.py

"""Детерминированное сочетание модификаторов эффекта (§12).

Без БД: проверяются стабильность порядка, причины и независимость
результата от порядка загрузки.
"""

import random
import unittest

from backend.app.modules.game_systems.rules.effect_stacking import (
	APPLIED,
	SUPPRESSED,
	EffectModifier,
	combine_modifier,
)


def mod(instance_id, value, stacking="stacking", code="ac", priority=0):
	return EffectModifier(instance_id=instance_id, code=code, value=value, stacking=stacking, priority=priority)


class EffectStackingTests(unittest.TestCase):
	def test_empty_returns_zero(self):
		total, outcomes = combine_modifier([])
		self.assertEqual(total, 0)
		self.assertEqual(outcomes, [])

	def test_stacking_sums_values(self):
		total, outcomes = combine_modifier([mod("i1", 2), mod("i2", 3)])
		self.assertEqual(total, 5)
		self.assertEqual([item.result for item in outcomes], [APPLIED, APPLIED])

	def test_same_code_different_instances_both_apply(self):
		"""Совпадение кода (названия) не отменяет второй экземпляр (§12)."""
		total, _ = combine_modifier([mod("i1", 2, code="ac"), mod("i2", 2, code="ac")])
		self.assertEqual(total, 4)

	def test_highest_selects_max(self):
		total, outcomes = combine_modifier([
			mod("i1", 2, "highest"),
			mod("i2", 5, "highest"),
			mod("i3", 1, "highest"),
		])
		self.assertEqual(total, 5)
		# highest — выбор одного значения, остальные поданы как
		# применённые в одну свёртку max; результат один.
		self.assertTrue(all(item.result == APPLIED for item in outcomes))

	def test_lowest_selects_min(self):
		total, _ = combine_modifier([mod("i1", 2, "lowest"), mod("i2", 5, "lowest")])
		self.assertEqual(total, 2)

	def test_override_suppresses_others(self):
		total, outcomes = combine_modifier([
			mod("i1", 2, "stacking"),
			mod("i2", 9, "override"),
			mod("i3", 4, "stacking"),
		])
		self.assertEqual(total, 9)
		by_id = {item.instance_id: item.result for item in outcomes}
		self.assertEqual(by_id["i2"], APPLIED)
		self.assertEqual(by_id["i1"], SUPPRESSED)
		self.assertEqual(by_id["i3"], SUPPRESSED)

	def test_override_priority_breaks_tie(self):
		total, _ = combine_modifier([
			mod("i1", 5, "override", priority=1),
			mod("i2", 7, "override", priority=9),
		])
		# больший приоритет выигрывает независимо от значения.
		self.assertEqual(total, 7)

	def test_unique_applies_one_per_code(self):
		total, outcomes = combine_modifier([
			mod("i1", 2, "unique", code="armor"),
			mod("i2", 3, "unique", code="armor"),
		])
		by_id = {item.instance_id: item.result for item in outcomes}
		# Применяется ровно один экземпляр на код.
		self.assertEqual(
			sorted(v for v in by_id.values()),
			[APPLIED, SUPPRESSED],
		)
		self.assertIn(total, (2, 3))

	def test_unique_different_codes_both_apply(self):
		total, _ = combine_modifier([
			mod("i1", 2, "unique", code="armor"),
			mod("i2", 3, "unique", code="shield"),
		])
		self.assertEqual(total, 5)

	def test_result_independent_of_input_order(self):
		"""Порядок загрузки из БД не определяет результат (§12)."""
		base = [
			mod("i1", 2, "stacking"),
			mod("i2", 3, "stacking"),
			mod("i3", 10, "highest"),
		]

		first_total, first = combine_modifier(base)

		for _ in range(20):
			shuffled = base[:]
			random.shuffle(shuffled)
			total, outcomes = combine_modifier(shuffled)
			self.assertEqual(total, first_total)
			self.assertEqual(
				[(item.instance_id, item.result) for item in outcomes],
				[(item.instance_id, item.result) for item in first],
			)

	def test_stable_order_by_priority_then_id(self):
		_, outcomes = combine_modifier([
			mod("zz", 1, "stacking", priority=0),
			mod("aa", 1, "stacking", priority=0),
			mod("hi", 1, "stacking", priority=5),
		])
		self.assertEqual(
			[item.instance_id for item in outcomes],
			["hi", "aa", "zz"],
		)

	def test_duplicate_instance_id_rejected(self):
		with self.assertRaises(ValueError):
			combine_modifier([mod("same", 1), mod("same", 2)])

	def test_unknown_stacking_rejected(self):
		with self.assertRaises(ValueError):
			combine_modifier([mod("i1", 1, "multiply")])

	def test_invalid_value_rejected(self):
		with self.assertRaises(ValueError):
			combine_modifier([mod("i1", 2_000_000_000)])

	def test_sum_overflow_rejected(self):
		with self.assertRaises(ValueError):
			combine_modifier([mod("i1", 900_000_000), mod("i2", 900_000_000)])

	def test_override_only_one_wins_even_with_unique(self):
		total, outcomes = combine_modifier([
			mod("i1", 2, "unique", code="armor"),
			mod("i2", 8, "override"),
		])
		self.assertEqual(total, 8)
		self.assertTrue(all(item.result == SUPPRESSED for item in outcomes if item.instance_id == "i1"))


if __name__ == "__main__":
	unittest.main()
