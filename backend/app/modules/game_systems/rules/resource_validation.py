# backend/app/modules/game_systems/rules/resource_validation.py

"""Проверка максимумов и начального заполнения ресурсов.

Не импортирует исполнители состояния, сервисы или модели БД.
"""

from __future__ import annotations
from backend.app.modules.game_systems.schemas.rules.rule_calculations import AttributePreviewResult, VALUE_LIMIT
from backend.app.modules.game_systems.schemas.rules.rule_resources import ResourceDefinitions


def resolve_resource_maxima(definitions: ResourceDefinitions, result: AttributePreviewResult) -> dict[str, int]:
    """Получить максимумы по уже выполненному числовому расчёту."""

    definitions = ResourceDefinitions.model_validate(definitions)

    namespaces = {
        "attribute": result.attributes,
        "stat": result.derived,
    }

    limits: dict[str, int] = {}

    for code, definition in definitions.resources.items():
        source = definition.maximum

        if type(source) is int:
            maximum = source
        else:
            namespace, target = source.split(".", 1)
            values = namespaces[namespace]

            if target not in values:
                raise ValueError(f"Ресурс {code}: неизвестная ссылка {source}")

            maximum = values[target]

        if type(maximum) is not int:
            raise ValueError(f"Ресурс {code}: максимум должен быть целым числом")

        if not 0 <= maximum <= VALUE_LIMIT:
            raise ValueError(f"Ресурс {code}: максимум вне допустимого неотрицательного диапазона")

        limits[code] = maximum

    return limits

def initial_resource_values(definitions: ResourceDefinitions, limits: dict[str, int]) -> dict[str, int]:
    """Создать начальные значения по уже проверенным максимумам."""

    definitions = ResourceDefinitions.model_validate(definitions)

    if set(limits) != set(definitions.resources):
        raise ValueError("Состав максимумов не соответствует определениям ресурсов")

    values: dict[str, int] = {}

    for code, definition in definitions.resources.items():
        maximum = limits[code]

        if type(maximum) is not int or not 0 <= maximum <= VALUE_LIMIT:
            raise ValueError(f"Ресурс {code}: недопустимый максимум")

        value = maximum if definition.initial == "full" else definition.initial

        if not 0 <= value <= maximum:
            raise ValueError(f"Ресурс {code}: начальный запас превышает вычисленный максимум")

        values[code] = value

    return values