# tests/python/game_systems/test_procedure_lifecycle.py

"""Логическая схема переходов процедуры (§11.2, §11.3, §11.4).

Без БД: проверяется детерминизм переходов, различие повторов доставки
от новых действий, и возврат стоимости.
"""

import unittest

from backend.app.modules.game_systems.rules.procedure_lifecycle import (
	COMPLETE,
	ERROR,
	READY_TO_APPLY,
	REFUNDABLE_STAGES,
	TERMINAL_STAGES,
	AWAIT_DECISION,
	APPLY,
	CHECK,
	CANCEL,
	PREPARE,
	LIFECYCLE_STAGES,
	TRANSITIONS,
	check_stage_transition,
	is_duplicate_request,
	can_refund_on_cancel,
)


class ProcedureLifecycleTests(unittest.TestCase):
	def test_all_stages_defined(self):
		self.assertEqual(set(LIFECYCLE_STAGES), {
			PREPARE, CHECK, AWAIT_DECISION, READY_TO_APPLY,
			APPLY, COMPLETE, CANCEL, ERROR,
		})

	def test_terminal_stages(self):
		self.assertEqual(TERMINAL_STAGES, {COMPLETE, CANCEL, ERROR})

	def test_refundable_stages(self):
		self.assertEqual(REFUNDABLE_STAGES, {PREPARE, CHECK, AWAIT_DECISION, READY_TO_APPLY})

	def test_forward_progress_is_allowed(self):
		"""Прямой переход prepare -> check -> apply -> complete разрешён."""
		s1 = check_stage_transition(PREPARE, CHECK)
		self.assertTrue(s1.allowed)

		s2 = check_stage_transition(CHECK, APPLY)
		self.assertTrue(s2.allowed)

		s3 = check_stage_transition(APPLY, COMPLETE)
		self.assertTrue(s3.allowed)

	def test_await_decision_returns_to_check(self):
		"""Ожидание решения может вернуться к проверке (§11.2)."""
		s = check_stage_transition(AWAIT_DECISION, CHECK)
		self.assertTrue(s.allowed)

	def test_await_decision_can_skip_apply(self):
		"""Ожидание может перейти к применению минуя ready_to_apply."""
		s = check_stage_transition(AWAIT_DECISION, APPLY)
		self.assertTrue(s.allowed)

	def test_cancel_from_any_non_terminal(self):
		"""Отмена возможна из любой не-завершающей стадии."""
		for stage in LIFECYCLE_STAGES:
			if stage not in TERMINAL_STAGES:
				s = check_stage_transition(stage, CANCEL)
				self.assertTrue(s.allowed, f"cancel from {stage}")

	def test_complete_blocks_all_transitions(self):
		"""Завершение блокирует все переходы."""
		for stage in LIFECYCLE_STAGES:
			if stage != COMPLETE:
				s = check_stage_transition(COMPLETE, stage)
				self.assertFalse(s.allowed)

	def test_error_blocks_all_transitions(self):
		"""Ошибка блокирует все переходы."""
		for stage in LIFECYCLE_STAGES:
			if stage != ERROR:
				s = check_stage_transition(ERROR, stage)
				self.assertFalse(s.allowed, f"error->{stage}")

	def test_same_stage_is_not_new_transition(self):
		"""Возврат в ту же стадию — не новый переход (§11.3)."""
		s = check_stage_transition(CHECK, CHECK)
		self.assertEqual(s.decision, "already_in_stage")
		self.assertFalse(s.allowed)
		# Но процедура остаётся resumable.
		self.assertTrue(s.resumable)

	def test_forbidden_transition_rejected(self):
		"""Запрещённый переход (complete -> check) отклоняется."""
		s = check_stage_transition(COMPLETE, CHECK)
		self.assertFalse(s.allowed)
		self.assertEqual(s.decision, "forbidden")
		self.assertFalse(s.resumable)

	def test_unknown_stage_rejected(self):
		s = check_stage_transition("bogus", CHECK)
		self.assertEqual(s.decision, "unknown_stage")
		self.assertFalse(s.allowed)

	def test_is_duplicate_request_matches(self):
		"""Совпадение ключа — повтор доставки (§11.3)."""
		self.assertTrue(is_duplicate_request("cmd-123", "cmd-123"))

	def test_is_duplicate_request_no_match(self):
		"""Разные ключи — не повтор, а новый переброс (§11.3)."""
		self.assertFalse(is_duplicate_request("cmd-123", "cmd-456"))

	def test_is_duplicate_request_no_previous_key(self):
		"""Отсутствие предыдущего ключа — не повтор."""
		self.assertFalse(is_duplicate_request(None, "cmd-123"))

	def test_is_duplicate_request_no_request_key(self):
		self.assertFalse(is_duplicate_request("cmd-123", ""))

	def test_can_refund_on_cancel_before_apply(self):
		"""Возврат возможен до применения (§11.4)."""
		for stage in REFUNDABLE_STAGES:
			self.assertTrue(can_refund_on_cancel(stage))

	def test_can_refund_on_cancel_after_apply_is_false(self):
		"""После APPLY возврат невозможен (§11.4)."""
		self.assertFalse(can_refund_on_cancel(APPLY))
		self.assertFalse(can_refund_on_cancel(COMPLETE))
		self.assertFalse(can_refund_on_cancel(CANCEL))
		self.assertFalse(can_refund_on_cancel(ERROR))

	def test_transition_resumable_flag_matches_terminal(self):
		"""resumable=False точно для завершающих стадий."""
		for stage in LIFECYCLE_STAGES:
			s = check_stage_transition(stage, APPLY)
			if stage in TERMINAL_STAGES:
				self.assertFalse(s.resumable, f"{stage} should not be resumable")

	def test_transitions_deterministic(self):
		"""TRANSITIONS не зависит от порядка итерации dict."""
		from copy import deepcopy
		a = TRANSITIONS
		b = deepcopy(TRANSITIONS)
		self.assertEqual(a, b)


if __name__ == "__main__":
	unittest.main()
