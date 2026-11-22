# backend/app/modules/game_systems/rules/procedure_lifecycle.py

"""Логическая схема переходов процедуры (§11.2, §11.3, §11.4).

Без БД, HTTP, проверки прав, бросков и правил конкретной системы.

Договор (§11.2) прямо указывает: перечисленные стадии — удобная
логическая схема, а не утверждённые имена существующих статусов.
Поэтому модуль оперирует абстрактными стадиями и не претендует на
соответствие реальным колонкам состояния.

Модуль отвечает только на два вопроса, которые можно проверить
детерминированно и без хранения:
- разрешён ли переход из текущей стадии в запрашиваемую (§11.2);
- является ли операция повтором доставки, а не новым действием,
  чтобы технический повтор не удваивал ни списание, ни возврат (§11.3, §11.4).

Сохранение контекста, ожидание решения и выполнение броска
принадлежат игровому процессу и выполняются вызывающим слоем.
"""

from __future__ import annotations

from typing import Literal

# Логические стадии схемы §11.2. Имена не являются статусами БД.
PREPARE = "prepare"
CHECK = "check"
AWAIT_DECISION = "await_decision"
READY_TO_APPLY = "ready_to_apply"
APPLY = "apply"
COMPLETE = "complete"
CANCEL = "cancel"
ERROR = "error"

LIFECYCLE_STAGES: tuple[str, ...] = (
	PREPARE,
	CHECK,
	AWAIT_DECISION,
	READY_TO_APPLY,
	APPLY,
	COMPLETE,
	CANCEL,
	ERROR,
)

# Стадии, из которых процедура не продолжается: они завершающие.
TERMINAL_STAGES: frozenset[str] = frozenset({COMPLETE, CANCEL, ERROR})

# Допустимые переходы логической схемы. Каждое ожидание может быть
# прервано отменой или ошибкой; возврат к проверке разрешён, потому
# что на каждом продолжении перепроверяются полномочия и условия (§11.2).
TRANSITIONS: dict[str, frozenset[str]] = {
	PREPARE: frozenset({CHECK, CANCEL, ERROR}),
	CHECK: frozenset({AWAIT_DECISION, READY_TO_APPLY, APPLY, CANCEL, ERROR}),
	AWAIT_DECISION: frozenset({READY_TO_APPLY, CHECK, APPLY, CANCEL, ERROR}),
	READY_TO_APPLY: frozenset({APPLY, CHECK, CANCEL, ERROR}),
	APPLY: frozenset({COMPLETE, ERROR, CANCEL}),
	COMPLETE: frozenset(),
	CANCEL: frozenset(),
	ERROR: frozenset(),
}

# Возврат стоимости возможен только до применения: после APPLY
# последствия уже согласованы и отмена не должна их удваивать (§11.4).
REFUNDABLE_STAGES: frozenset[str] = frozenset({PREPARE, CHECK, AWAIT_DECISION, READY_TO_APPLY})

TransitionDecision = Literal["allowed", "already_in_stage", "forbidden", "unknown_stage"]


class StageTransition:
    """Решение о переходе с объяснением (§11.2)."""

    __slots__ = ("decision", "from_stage", "to_stage", "resumable")

    def __init__(self, decision: str, from_stage: str, to_stage: str, resumable: bool) -> None:
        self.decision = decision
        self.from_stage = from_stage
        self.to_stage = to_stage
        self.resumable = resumable

    @property
    def allowed(self) -> bool:
        return self.decision == "allowed"

    def __repr__(self) -> str:
        return (
            f"<StageTransition(decision={self.decision!r}, "
            f"from_stage={self.from_stage!r}, to_stage={self.to_stage!r})>"
        )


def check_stage_transition(current_stage: str, requested_stage: str) -> StageTransition:
    """Проверить переход между логическими стадиями процедуры.

    Возврат в ту же стадию не является новым переходом: повтор
    доставки того же шага должен вернуться к уже достигнутому
    состоянию, а не выполнить действие второй раз (§11.3, §11.4).
    """

    if current_stage not in TRANSITIONS:
        return StageTransition("unknown_stage", current_stage, requested_stage, False)

    if requested_stage not in TRANSITIONS:
        return StageTransition("unknown_stage", current_stage, requested_stage, False)

    resumable = current_stage not in TERMINAL_STAGES

    if current_stage == requested_stage:
        return StageTransition("already_in_stage", current_stage, requested_stage, resumable)

    if requested_stage in TRANSITIONS[current_stage]:
        return StageTransition("allowed", current_stage, requested_stage, resumable)

    return StageTransition("forbidden", current_stage, requested_stage, resumable)


def is_duplicate_request(previous_key: str | None, request_key: str) -> bool:
    """Отличить повтор доставки команды от нового действия (§11.3).

    Совпадение ключа запроса означает повтор доставки: результат уже
    получен и не должен вычисляться или списываться заново. Новый
    переброс по правилам системы приходит с другим ключом и является
    отдельной операцией с собственной стоимостью.

    Отсутствующий ключ не считается повтором: вызывающий код обязан
    передать идентичность команды.
    """

    if previous_key is None or not request_key:
        return False

    return previous_key == request_key


def can_refund_on_cancel(stage: str) -> bool:
    """Разрешён ли возврат стоимости на текущей стадии (§11.4).

    Отмена возвращает стоимость только тогда, когда это предусмотрено
    правилами и стадией процедуры. После APPLY возврат не выполняется,
    чтобы технический повтор не удвоил ни списание, ни возврат.
    """

    if stage not in TRANSITIONS:
        raise ValueError(f"Неизвестная стадия процедуры: {stage}")

    return stage in REFUNDABLE_STAGES


__all__ = [
    "LIFECYCLE_STAGES",
    "TERMINAL_STAGES",
    "TRANSITIONS",
    "REFUNDABLE_STAGES",
    "StageTransition",
    "check_stage_transition",
    "is_duplicate_request",
    "can_refund_on_cancel",
    "PREPARE",
    "CHECK",
    "AWAIT_DECISION",
    "READY_TO_APPLY",
    "APPLY",
    "COMPLETE",
    "CANCEL",
    "ERROR",
]
