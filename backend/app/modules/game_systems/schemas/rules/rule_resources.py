# backend/app/modules/game_systems/schemas/rules/rule_resources.py

"""Определения и состояние целочисленных ресурсов.

Не содержит правил конкретной игровой системы.
Определения ресурсов отделены от их текущих значений.
"""

from __future__ import annotations
from typing import Annotated, Literal
from pydantic import Field, model_validator
from backend.app.modules.game_systems.schemas.rules.rule_calculations import (CalculationModel, CalculationValue, Code, VALUE_LIMIT)


MAX_RESOURCES = 128

NonNegativeAmount = Annotated[
    int,
    Field(ge=0, le=VALUE_LIMIT),
]

PositiveAmount = Annotated[
    int,
    Field(ge=1, le=VALUE_LIMIT),
]

NumericReference = Annotated[
    str,
    Field(
        pattern=r"^(attribute|stat)\.[a-z][a-z0-9_]{0,39}$"
    ),
]

class ResourceDefinition(CalculationModel):
    """Определение одного ресурса.

    maximum:
        Целое число либо ссылка на результат числового расчёта.

    initial:
        "full" — заполнить до максимума при создании;
        число — явно заданный начальный запас.

    recovery:
        Соответствие кода события способу восстановления.
        "full" — заполнить до максимума;
        положительное число — восстановить это количество.
    """

    label: str = Field(min_length=1, max_length=100, pattern=r"\S",)
    description: str = Field(default="", strict=True, max_length=10000)

    maximum: CalculationValue | NumericReference

    initial: NonNegativeAmount | Literal["full"] = "full"

    recovery: dict[
        Code,
        PositiveAmount | Literal["full"],
    ] = Field(
        default_factory=dict,
        max_length=128,
    )

    @model_validator(mode="after")
    def validate_fixed_maximum(self):
        if type(self.maximum) is int:
            if self.maximum < 0:
                raise ValueError(
                    "Максимум ресурса не может быть отрицательным"
                )

            if (
                    type(self.initial) is int
                    and self.initial > self.maximum
            ):
                raise ValueError(
                    "Начальный запас превышает максимум ресурса"
                )

        return self

class ResourceDefinitions(CalculationModel):
    """Самостоятельный раздел определений ресурсов."""

    resources: dict[Code, ResourceDefinition] = Field(
        default_factory=dict,
        max_length=MAX_RESOURCES,
    )

class ResourceState(CalculationModel):
    """Текущие значения ресурсов, без их определений."""

    schema_version: Literal[1] = 1

    values: dict[Code, NonNegativeAmount] = Field(
        default_factory=dict,
        max_length=MAX_RESOURCES,
    )

class ResourceAmounts(CalculationModel):
    """Положительные количества для расхода или восстановления.

    Нулевые операции не передаются.
    Это не абсолютные новые значения ресурсов.
    """

    amounts: dict[Code, PositiveAmount] = Field(
        min_length=1,
        max_length=MAX_RESOURCES,
    )

class ResourceRecoveryEvent(CalculationModel):
    """Явно переданное событие восстановления."""

    code: Code