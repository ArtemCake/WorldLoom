# backend/app/modules/characters/schemas/effect_schemas.py

"""Контракты экземпляров эффектов и журнала причин (Этап F3, §12).

Экземпляр хранит изменения и правила сочетания данными, а не
вычисленным итогом: итог сворачивает ядро effect_stacking по
активным экземплярам. Чтение возвращает и экземпляр, и свёртку
раздельно, чтобы не появлялся второй источник правды об итоге (§12).

Журнал описывает уже выполненные наложение, продление, подавление и
снятие; он не участвует в вычислении свёртки.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Правила сочетания совпадают с ядром effect_stacking (§12).
StackingRule = Literal["stacking", "highest", "lowest", "override", "unique"]

# Жизненный статус экземпляра.
EffectStatus = Literal["active", "suppressed", "withdrawn"]

# Причины в журнале причин (§12).
EffectReasonType = Literal["apply", "extend", "suppress", "withdraw"]

# Результат участия экземпляра в свёртке (из ядра effect_stacking).
ModifierResult = Literal["applied", "suppressed"]


class EffectModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


# ---------- изменение эффекта (§12) ----------


class EffectModifierIn(EffectModel):
    """Одно изменение экземпляра: показатель, величина и правило сочетания.

    Совпадение кода с другим экземпляром не объединяет их: идентичность
    даёт экземпляр, а не код (§12).
    """

    code: str = Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_]*$")
    value: int = Field(ge=-1_000_000_000, le=1_000_000_000)
    stacking: StackingRule = "stacking"
    priority: int = Field(default=0, ge=-1_000_000, le=1_000_000)


# ---------- наложение экземпляра (§12) ----------


class EffectInstanceApplyIn(EffectModel):
    """Запрос наложить эффект на цель.

    application_key — идемпотентный ключ события наложения: повторная
    обработка того же события переиспользует экземпляр, а не создаёт
    копию (§12). Без ключа наложение не идемпотентно.
    """

    source_type: str = Field(min_length=1, max_length=30, pattern=r"^[a-z][a-z0-9_]*$")
    source_id: UUID | None = None
    effect_id: UUID | None = None
    application_key: UUID | None = None
    modifiers: list[EffectModifierIn] = Field(min_length=1, max_length=128)
    conditions: dict | None = None
    duration_value: int | None = Field(default=None, ge=0)
    duration_unit: str | None = Field(default=None, min_length=1, max_length=20)
    end_events: list[str] | None = Field(default=None, max_length=64)
    started_event: str | None = Field(default=None, min_length=1, max_length=100)
    comment: str | None = None


class EffectExtendIn(EffectModel):
    """Продление длительности существующего экземпляра (§12)."""

    duration_delta: int = Field(ge=1)
    comment: str | None = None


# ---------- чтение экземпляра (§12) ----------


class EffectInstanceRead(EffectModel):
    """Текущее состояние экземпляра эффекта на цели."""

    id: UUID
    status: EffectStatus
    effect_id: UUID | None
    source_type: str
    source_id: UUID | None
    application_key: UUID | None
    duration_value: int | None
    duration_unit: str | None
    started_event: str | None
    started_at: datetime
    ended_at: datetime | None


class EffectInstancesRead(EffectModel):
    """Пакет экземпляров владельца."""

    items: list[EffectInstanceRead]


# ---------- свёртка эффектов (§12) ----------


class EffectOutcomeRead(EffectModel):
    """Причина участия одного экземпляра в свёртке показателя (§12)."""

    instance_id: UUID
    code: str
    value: int
    stacking: StackingRule
    result: ModifierResult


class EffectAggregateRead(EffectModel):
    """Итог по одному показателю и причины по экземплярам (§12)."""

    code: str
    total: int
    outcomes: list[EffectOutcomeRead]


class EffectAggregationRead(EffectModel):
    """Свёртка активных экземпляров цели по всем показателям."""

    items: list[EffectAggregateRead]


# ---------- журнал причин (§12) ----------


class EffectChangeRead(EffectModel):
    """Одна запись журнала причин (append-only)."""

    id: UUID
    instance_id: UUID | None
    reason_type: EffectReasonType
    status_before: EffectStatus | None
    status_after: EffectStatus
    event_code: str | None
    request_id: UUID | None
    source_type: str | None
    source_id: UUID | None
    comment: str | None
    created_at: datetime


class EffectChangesRead(EffectModel):
    """Пакет записей журнала владельца."""

    items: list[EffectChangeRead]


__all__ = [
    "StackingRule",
    "EffectStatus",
    "EffectReasonType",
    "ModifierResult",
    "EffectModifierIn",
    "EffectInstanceApplyIn",
    "EffectExtendIn",
    "EffectInstanceRead",
    "EffectInstancesRead",
    "EffectOutcomeRead",
    "EffectAggregateRead",
    "EffectAggregationRead",
    "EffectChangeRead",
    "EffectChangesRead",
]
