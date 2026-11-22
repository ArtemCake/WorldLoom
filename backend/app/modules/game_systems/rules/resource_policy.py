# backend/app/modules/game_systems/rules/resource_policy.py

"""Явная политика ограничения запаса ресурса при изменении максимума.

Без БД, HTTP, проверки прав и правил конкретной системы.
Переданное состояние не изменяется.

Договор (§10): после изменения максимума применяется явная политика
ограничения текущего значения; она не выбирается случайно в разных
экранах. Причина каждого изменения возвращается отдельно и попадает
в журнал вызывающим кодом.

Политики ограничения (не пополнение — пополнение описано событиями
восстановления в rule_resources.ResourceDefinition.recovery):
- "clamp": значение не может превышать действующий максимум;
- "keep": значение сохраняется даже сверх нового максимума,
  когда система допускает временное переполнение.
"""

from __future__ import annotations

from typing import Literal

from backend.app.modules.game_systems.schemas.rules.rule_calculations import VALUE_LIMIT
from backend.app.modules.game_systems.schemas.rules.rule_resources import ResourceDefinitions
from backend.app.modules.game_systems.schemas.rules.rule_resources import ResourceState as State

ResourceLimitPolicy = Literal["clamp", "keep"]

POLICIES: tuple[str, ...] = ("clamp", "keep")


class ResourceLimitAdjustment:
    """Причина изменения запаса одного ресурса после смены максимума.

    Значение clamped означает, что запас был ограничен новым
    максимумом. Переполнение (keep) тоже фиксируется как событие,
    потому что запас остался выше действующего максимума.
    """

    __slots__ = ("code", "previous_value", "value", "previous_maximum", "maximum", "clamped")

    def __init__(
        self,
        code: str,
        previous_value: int,
        value: int,
        previous_maximum: int,
        maximum: int,
        clamped: bool,
    ) -> None:
        self.code = code
        self.previous_value = previous_value
        self.value = value
        self.previous_maximum = previous_maximum
        self.maximum = maximum
        self.clamped = clamped

    def __repr__(self) -> str:
        return (
            f"<ResourceLimitAdjustment(code={self.code!r}, "
            f"previous_value={self.previous_value!r}, value={self.value!r}, "
            f"clamped={self.clamped!r})>"
        )


def _check_policy(policy: str) -> None:
    if policy not in POLICIES:
        raise ValueError(
            "Неизвестная политика ограничения запаса: "
            + f"{policy}. Допустимо: "
            + ", ".join(POLICIES)
        )


def apply_limit_policy(
    definitions: ResourceDefinitions,
    previous_maximums: dict[str, int],
    state: State,
    maximums: dict[str, int],
    policy: str,
) -> tuple[State, list[ResourceLimitAdjustment]]:
    """Ограничить запас ресурсов по новому максимуму согласно политике.

    previous_maximums — максимумы, при которых был получен текущий
    запас; используются только для журнала. maximums — действующие
    максимумы. Возвращает новое состояние и список причин изменений
    в стабильном порядке по коду ресурса.

    Состав ресурсов должен совпадать с определениями: политика не
    добавляет и не удаляет ресурсы.
    """

    definitions = ResourceDefinitions.model_validate(definitions)
    state = State.model_validate(state)
    _check_policy(policy)

    expected = set(definitions.resources)
    received = set(state.values)

    missing = sorted(expected - received)
    unknown = sorted(received - expected)

    if missing or unknown:
        problems: list[str] = []

        if missing:
            problems.append("отсутствуют ресурсы: " + ", ".join(missing))

        if unknown:
            problems.append("неизвестные ресурсы: " + ", ".join(unknown))

        raise ValueError("; ".join(problems))

    if set(maximums) != expected:
        raise ValueError("Состав новых максимумов не соответствует определениям ресурсов")

    values = dict(state.values)
    adjustments: list[ResourceLimitAdjustment] = []

    for code in sorted(expected):
        maximum = maximums[code]

        if type(maximum) is not int or not 0 <= maximum <= VALUE_LIMIT:
            raise ValueError(f"Ресурс {code}: недопустимый новый максимум")

        previous_value = values[code]
        previous_maximum = previous_maximums.get(code, previous_value)

        if policy == "clamp":
            value = min(previous_value, maximum)
        else:
            value = previous_value

        clamped = value != previous_value

        if clamped or value > maximum:
            adjustments.append(
                ResourceLimitAdjustment(
                    code=code,
                    previous_value=previous_value,
                    value=value,
                    previous_maximum=previous_maximum,
                    maximum=maximum,
                    clamped=clamped,
                )
            )

        values[code] = value

    return State(values=values), adjustments


__all__ = [
    "ResourceLimitPolicy",
    "ResourceLimitAdjustment",
    "apply_limit_policy",
    "POLICIES",
]
