# backend/app/modules/game_systems/rules/effect_stacking.py

"""Детерминированное сочетание модификаторов эффекта (§12).

Без БД, HTTP, проверки прав и правил конкретной системы.
Правила сочетания передаются данными вместе с модификаторами,
поэтому модуль не зависит от того, где и как эффекты хранятся.

Договор (§12):
- удаление одного экземпляра не снимает другой только из-за
  совпадения названия — идентичность даёт instance_id, а не имя;
- сочетание определяется явными правилами: суммирование, выбор
  одного, подавление, замещение или иной поддержанный механизм;
- порядок загрузки из БД не определяет результат — свёртка
  упорядочена стабильно и не зависит от порядка входа.

Результат содержит итоговое значение и причину по каждому
модификатору, чтобы вызывающий код записал журнал наложения,
подавления и снятия (§12).
"""

from __future__ import annotations

from typing import Literal

from backend.app.modules.game_systems.schemas.rules.rule_calculations import VALUE_LIMIT

# Поддержанные механизмы сочетания для одного показателя.
StackingRule = Literal["stacking", "highest", "lowest", "override", "unique"]

STACKING_RULES: tuple[str, ...] = ("stacking", "highest", "lowest", "override", "unique")

# Итоговые состояния модификатора в свёртке.
APPLIED = "applied"
SUPPRESSED = "suppressed"


class EffectModifier:
    """Один экземпляр модификатора эффекта на показателе.

    instance_id — идентичность экземпляра: совпадение кода или
    названия не делает два экземпляра одним (§12).
    stacking — механизм сочетания этого экземпляра.
    priority — детерминированный признак для правил, где важен
    порядок (override); при равенстве решает стабильный instance_id.
    """

    __slots__ = ("instance_id", "code", "value", "stacking", "priority")

    def __init__(
        self,
        instance_id: str,
        code: str,
        value: int,
        stacking: str = "stacking",
        priority: int = 0,
    ) -> None:
        self.instance_id = instance_id
        self.code = code
        self.value = value
        self.stacking = stacking
        self.priority = priority

    def __repr__(self) -> str:
        return (
            f"<EffectModifier(instance_id={self.instance_id!r}, "
            f"code={self.code!r}, value={self.value!r}, "
            f"stacking={self.stacking!r})>"
        )


class ModifierOutcome:
    """Причина участия одного экземпляра в свёртке (§12 журнал)."""

    __slots__ = ("instance_id", "code", "value", "result")

    def __init__(self, instance_id: str, code: str, value: int, result: str) -> None:
        self.instance_id = instance_id
        self.code = code
        self.value = value
        self.result = result

    def __repr__(self) -> str:
        return (
            f"<ModifierOutcome(instance_id={self.instance_id!r}, "
            f"result={self.result!r})>"
        )


def _validate(modifiers: list[EffectModifier]) -> None:
    seen: set[str] = set()

    for modifier in modifiers:
        if modifier.stacking not in STACKING_RULES:
            raise ValueError(
                f"Эффект {modifier.instance_id}: неизвестное правило "
                f"сочетания {modifier.stacking}. "
                "Допустимо: " + ", ".join(STACKING_RULES)
            )

        if type(modifier.value) is not int or not -VALUE_LIMIT <= modifier.value <= VALUE_LIMIT:
            raise ValueError(f"Эффект {modifier.instance_id}: недопустимое значение")

        if modifier.instance_id in seen:
            raise ValueError(
                f"Повторяется идентичность экземпляра: {modifier.instance_id}"
            )

        seen.add(modifier.instance_id)


def _stable_order(modifiers: list[EffectModifier]) -> list[EffectModifier]:
    """Порядок, не зависящий от порядка загрузки из БД (§12)."""
    return sorted(modifiers, key=lambda item: (-item.priority, item.instance_id))


def combine_modifier(modifiers: list[EffectModifier]) -> tuple[int, list[ModifierOutcome]]:
    """Свернуть модификаторы одного показателя в одно значение.

    Смешанные правила сочетания разрешаются по приоритету:
    - если есть override, действует только он (наивысший приоритет),
      остальные подавлены;
    - unique допускает один экземпляр, дубликат подавляется;
    - highest/lowest выбирают крайнее из стекируемых;
    - stacking складывает значения.

    Возвращает итог и причину по каждому экземпляру в стабильном
    порядке. Пустой список даёт ноль без изменений.
    """

    _validate(modifiers)

    if not modifiers:
        return 0, []

    ordered = _stable_order(modifiers)
    outcomes: dict[str, ModifierOutcome] = {}

    overrides = [item for item in ordered if item.stacking == "override"]

    if overrides:
        winner = overrides[0]

        for item in ordered:
            result = APPLIED if item is winner else SUPPRESSED
            outcomes[item.instance_id] = ModifierOutcome(item.instance_id, item.code, item.value, result)

        return winner.value, [outcomes[item.instance_id] for item in ordered]

    uniques = [item for item in ordered if item.stacking == "unique"]

    if uniques:
        # unique: среди экземпляров одного кода действует только один
        # (стабильно первый); совпадение названия не отменяет этот
        # выбор, решает идентичность экземпляра (§12).
        chosen: set[str] = set()

        for item in ordered:
            if item.stacking != "unique":
                outcomes[item.instance_id] = ModifierOutcome(
                    item.instance_id, item.code, item.value, APPLIED
                )
                continue

            if item.code in chosen:
                outcomes[item.instance_id] = ModifierOutcome(
                    item.instance_id, item.code, item.value, SUPPRESSED
                )
            else:
                chosen.add(item.code)
                outcomes[item.instance_id] = ModifierOutcome(
                    item.instance_id, item.code, item.value, APPLIED
                )

        applied = [item for item in ordered if outcomes[item.instance_id].result == APPLIED]
        total = sum(item.value for item in applied)

        if not -VALUE_LIMIT <= total <= VALUE_LIMIT:
            raise ValueError("Итоговое значение модификаторов вне допустимого диапазона")

        return total, [outcomes[item.instance_id] for item in ordered]

    stackable = [item for item in ordered if item.stacking in {"stacking", "highest", "lowest"}]

    for item in stackable:
        outcomes[item.instance_id] = ModifierOutcome(item.instance_id, item.code, item.value, APPLIED)

    if not stackable:
        for item in ordered:
            outcomes[item.instance_id] = ModifierOutcome(item.instance_id, item.code, item.value, SUPPRESSED)

        return 0, [outcomes[item.instance_id] for item in ordered]

    if any(item.stacking == "highest" for item in stackable):
        total = max(item.value for item in stackable)
    elif any(item.stacking == "lowest" for item in stackable):
        total = min(item.value for item in stackable)
    else:
        total = sum(item.value for item in stackable)

    if not -VALUE_LIMIT <= total <= VALUE_LIMIT:
        raise ValueError("Итоговое значение модификаторов вне допустимого диапазона")

    return total, [outcomes[item.instance_id] for item in ordered]


__all__ = [
    "EffectModifier",
    "ModifierOutcome",
    "combine_modifier",
    "STACKING_RULES",
    "StackingRule",
    "APPLIED",
    "SUPPRESSED",
]
