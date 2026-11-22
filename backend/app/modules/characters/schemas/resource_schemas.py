# backend/app/modules/characters/schemas/resource_schemas.py

"""Контракты значений ресурсов и журнала причин (Этап F2, §10).

Значение и максимум читаются раздельно: максимум вычисляет ядро по
закреплённой публикации, а в таблице хранится только текущий запас.
Совмещение двух чисел в одной модели было бы вторым источником правды.

Журнал описывает уже выполненные изменения и служит причиной каждого
из них; он не участвует в вычислении текущего запаса.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


ResourceReasonType = Literal[
    "init",
    "spend",
    "restore",
    "recover",
    "limit",
    "manual",
]


class ResourceModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class ResourceValueRead(ResourceModel):
    """Текущий запас одного ресурса вместе с действующим максимумом."""

    code: str
    value: int
    maximum: int


class ResourceValuesRead(ResourceModel):
    """Пакет текущих запасов владельца."""

    items: list[ResourceValueRead]


class ResourceChangeRead(ResourceModel):
    """Одна запись журнала причин (append-only)."""

    id: UUID
    code: str
    reason_type: ResourceReasonType
    previous_value: int
    value: int
    delta: int
    maximum: int | None = None
    event_code: str | None = None
    source_type: str | None = None
    source_id: UUID | None = None
    comment: str | None = None
    created_at: datetime


class ResourceChangesRead(ResourceModel):
    """Пакет записей журнала владельца."""

    items: list[ResourceChangeRead]


__all__ = [
    "ResourceReasonType",
    "ResourceValueRead",
    "ResourceValuesRead",
    "ResourceChangeRead",
    "ResourceChangesRead",
]
