# backend/app/modules/game_systems/rules/resource_engine.py

"""Чистые операции с целочисленными ресурсами.

Без БД, HTTP, проверки прав и правил конкретной системы.
Переданное состояние не изменяется.
"""

from __future__ import annotations
from backend.app.modules.game_systems.rules.resource_validation import initial_resource_values, resolve_resource_maxima
from backend.app.modules.game_systems.rules.rules_engine import evaluate_sheet_state
from backend.app.modules.game_systems.schemas.game_rules import RulesProfile, SheetState
from backend.app.modules.game_systems.schemas.rules.rule_resources import ResourceAmounts as Amounts
from backend.app.modules.game_systems.schemas.rules.rule_resources import ResourceDefinitions as Definitions
from backend.app.modules.game_systems.schemas.rules.rule_resources import ResourceRecoveryEvent
from backend.app.modules.game_systems.schemas.rules.rule_resources import ResourceState as State


def resolve_resource_limits(profile: RulesProfile, sheet: SheetState, definitions: Definitions) -> dict[str, int]:
    """Проверить определения и вычислить максимумы для текущего листа."""

    definitions = Definitions.model_validate(definitions)
    result = evaluate_sheet_state(profile, sheet)

    return resolve_resource_maxima(definitions, result)

def _validated_values(definitions: Definitions, limits: dict[str, int], state: State) -> dict[str, int]:
    """Проверить полный состав и текущие значения ресурсов."""

    state = State.model_validate(state)

    expected = set(definitions.resources)
    received = set(state.values)

    missing = sorted(expected - received)
    unknown = sorted(received - expected)

    problems: list[str] = []

    if missing:
        problems.append("отсутствуют ресурсы: " + ", ".join(missing))

    if unknown:
        problems.append("неизвестные ресурсы: " + ", ".join(unknown))

    if problems:
        raise ValueError("; ".join(problems))

    for code, value in state.values.items():
        if value > limits[code]:
            raise ValueError(f"Ресурс {code}: текущий запас {value} превышает максимум {limits[code]}")

    return dict(state.values)

def _prepare(profile: RulesProfile, sheet: SheetState, definitions: Definitions, state: State):
    """Проверить определения и состояние перед изменением."""

    definitions = Definitions.model_validate(definitions)
    limits = resolve_resource_limits(profile, sheet, definitions)
    values = _validated_values(definitions, limits, state)

    return definitions, limits, values

def _validate_amount_codes(definitions: Definitions, amounts: Amounts) -> None:
    unknown = sorted(set(amounts.amounts) - set(definitions.resources))

    if unknown:
        raise ValueError("Неизвестные ресурсы: " + ", ".join(unknown))

def create_resource_state(profile: RulesProfile, sheet: SheetState, definitions: Definitions) -> State:
    """Создать запас из явно настроенных начальных значений."""

    definitions = Definitions.model_validate(definitions)
    limits = resolve_resource_limits(profile, sheet, definitions)
    values = initial_resource_values(definitions, limits)

    return State(values=values)

def validate_resource_state(profile: RulesProfile, sheet: SheetState, definitions: Definitions, state: State) -> State:
    """Проверить состояние и вернуть отдельный экземпляр."""

    _, _, values = _prepare(profile, sheet, definitions, state)

    return State(values=values)

def spend_resources(profile: RulesProfile, sheet: SheetState, definitions: Definitions, state: State, amounts: Amounts) -> State:
    """Потратить ресурсы, только если хватает всего запрошенного запаса."""

    definitions, _, values = _prepare(profile, sheet, definitions, state)
    amounts = Amounts.model_validate(amounts)

    _validate_amount_codes(definitions, amounts)

    for code, amount in amounts.amounts.items():
        if amount > values[code]:
            raise ValueError(f"Недостаточно ресурса {code}: нужно {amount}, доступно {values[code]}")

    for code, amount in amounts.amounts.items():
        values[code] -= amount

    return State(values=values)

def restore_resources(profile: RulesProfile, sheet: SheetState, definitions: Definitions, state: State, amounts: Amounts) -> State:
    """Восстановить заданное количество, не превышая максимум."""

    definitions, limits, values = _prepare(profile, sheet, definitions, state)
    amounts = Amounts.model_validate(amounts)

    _validate_amount_codes(definitions, amounts)

    for code, amount in amounts.amounts.items():
        values[code] = min(limits[code], values[code] + amount)

    return State(values=values)

def recover_resources(profile: RulesProfile, sheet: SheetState, definitions: Definitions, state: State, event: str) -> State:
    """Применить восстановление по уже подтверждённому событию.

    Условия наступления события проверяет вызывающая процедура.
    Ресурсы без настройки для события остаются прежними.
    """

    event_code = ResourceRecoveryEvent(code=event).code
    definitions, limits, values = _prepare(profile, sheet, definitions, state)

    for code, definition in definitions.resources.items():
        recovery = definition.recovery.get(event_code)

        if recovery is None:
            continue

        if recovery == "full":
            values[code] = limits[code]
        else:
            values[code] = min(limits[code], values[code] + recovery)

    return State(values=values)


__all__ = [
    "resolve_resource_limits",
    "create_resource_state",
    "validate_resource_state",
    "spend_resources",
    "restore_resources",
    "recover_resources",
]