# tests/python/game_systems/test_resource_policy.py

"""Чистые проверки явной политики ограничения запаса ресурса (§10).

Без БД: проверяются только детерминизм и причины изменений.
"""

import unittest

from backend.app.modules.game_systems.rules.resource_policy import (
	POLICIES,
	apply_limit_policy,
)
from backend.app.modules.game_systems.schemas.rules.rule_resources import (
	ResourceDefinitions,
	ResourceState,
)


def make_definitions():
	# Искусственный пример для проверки ядра, а не правила конкретной системы.
	return ResourceDefinitions.model_validate({
		"resources": {
			"focus": {"label": "Сосредоточение", "maximum": 6, "initial": "full"},
			"supplies": {"label": "Припасы", "maximum": 4, "initial": 1},
		},
	})


class ResourcePolicyTests(unittest.TestCase):
	def setUp(self):
		self.definitions = make_definitions()

	def state(self, focus, supplies):
		return ResourceState(values={"focus": focus, "supplies": supplies})

	def test_clamp_limits_value_to_new_maximum(self):
		previous = {"focus": 6, "supplies": 4}
		new_maximums = {"focus": 3, "supplies": 4}

		updated, adjustments = apply_limit_policy(
			self.definitions, previous, self.state(6, 4), new_maximums, "clamp"
		)

		self.assertEqual(updated.values, {"focus": 3, "supplies": 4})
		self.assertEqual([item.code for item in adjustments], ["focus"])
		self.assertTrue(adjustments[0].clamped)
		self.assertEqual(adjustments[0].previous_value, 6)
		self.assertEqual(adjustments[0].value, 3)
		self.assertEqual(adjustments[0].maximum, 3)

	def test_keep_preserves_overflow_but_records_reason(self):
		previous = {"focus": 6, "supplies": 4}
		new_maximums = {"focus": 3, "supplies": 4}

		updated, adjustments = apply_limit_policy(
			self.definitions, previous, self.state(6, 4), new_maximums, "keep"
		)

		# Значение сохранено выше нового максимума, но причина зафиксирована.
		self.assertEqual(updated.values, {"focus": 6, "supplies": 4})
		self.assertEqual(len(adjustments), 1)
		self.assertFalse(adjustments[0].clamped)
		self.assertEqual(adjustments[0].value, 6)
		self.assertGreater(adjustments[0].value, adjustments[0].maximum)

	def test_raised_maximum_produces_no_adjustment(self):
		previous = {"focus": 2, "supplies": 1}
		new_maximums = {"focus": 9, "supplies": 9}

		updated, adjustments = apply_limit_policy(
			self.definitions, previous, self.state(2, 1), new_maximums, "clamp"
		)

		self.assertEqual(updated.values, {"focus": 2, "supplies": 1})
		self.assertEqual(adjustments, [])

	def test_input_state_not_mutated(self):
		state = self.state(6, 4)
		before = state.model_dump()

		apply_limit_policy(
			self.definitions,
			{"focus": 6, "supplies": 4},
			state,
			{"focus": 1, "supplies": 1},
			"clamp",
		)

		self.assertEqual(state.model_dump(), before)

	def test_adjustments_ordered_by_code(self):
		# Оба ресурса ограничены — порядок стабилен по коду, не по вставке.
		updated, adjustments = apply_limit_policy(
			self.definitions,
			{"focus": 6, "supplies": 4},
			self.state(6, 4),
			{"focus": 1, "supplies": 2},
			"clamp",
		)

		self.assertEqual([item.code for item in adjustments], ["focus", "supplies"])
		self.assertEqual(updated.values, {"focus": 1, "supplies": 2})

	def test_unknown_policy_is_rejected(self):
		with self.assertRaises(ValueError):
			apply_limit_policy(
				self.definitions,
				{"focus": 6, "supplies": 4},
				self.state(6, 4),
				{"focus": 1, "supplies": 1},
				"truncate",
			)

	def test_missing_resource_in_state_is_rejected(self):
		with self.assertRaises(ValueError):
			apply_limit_policy(
				self.definitions,
				{"focus": 6},
				ResourceState(values={"focus": 6}),
				{"focus": 3, "supplies": 4},
				"clamp",
			)

	def test_unknown_resource_in_state_is_rejected(self):
		with self.assertRaises(ValueError):
			apply_limit_policy(
				self.definitions,
				{"focus": 6, "supplies": 4},
				ResourceState(values={"focus": 6, "supplies": 4, "extra": 1}),
				{"focus": 3, "supplies": 4},
				"clamp",
			)

	def test_mismatched_maximums_composition_is_rejected(self):
		with self.assertRaises(ValueError):
			apply_limit_policy(
				self.definitions,
				{"focus": 6, "supplies": 4},
				self.state(6, 4),
				{"focus": 3},
				"clamp",
			)

	def test_negative_new_maximum_is_rejected(self):
		with self.assertRaises(ValueError):
			apply_limit_policy(
				self.definitions,
				{"focus": 6, "supplies": 4},
				self.state(6, 4),
				{"focus": -1, "supplies": 4},
				"clamp",
			)

	def test_policies_constant_lists_supported(self):
		self.assertEqual(set(POLICIES), {"clamp", "keep"})


if __name__ == "__main__":
	unittest.main()
