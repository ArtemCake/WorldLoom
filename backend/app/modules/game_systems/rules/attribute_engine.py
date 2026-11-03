# backend/app/modules/game_systems/rules/attribute_engine.py

"""Расчёт пользовательских показателей по графу зависимостей."""

from __future__ import annotations
from backend.app.modules.game_systems.rules.formula_engine import (evaluate_formula)
from backend.app.modules.game_systems.schemas.rule_calculations import (AttributePreviewInput, AttributePreviewResult, CalculationStep)


def evaluate_attributes(data: AttributePreviewInput) -> AttributePreviewResult:
	"""Выполнить чистый расчёт без сохранения состояния и бросков."""
	data = AttributePreviewInput.model_validate(data)
	config = data.calculations

	expected = set(config.attributes)
	received = set(data.attributes)

	if expected != received:
		problems: list[str] = []

		missing = sorted(expected - received)
		unknown = sorted(received - expected)

		if missing:
			problems.append(
				"не заданы показатели: " + ", ".join(missing)
			)

		if unknown:
			problems.append(
				"неизвестные показатели: " + ", ".join(unknown)
			)

		raise ValueError("; ".join(problems))

	context: dict[str, int] = {}

	for code, definition in config.attributes.items():
		value = data.attributes[code]

		if not definition.min_value <= value <= definition.max_value:
			raise ValueError(
				f"Показатель {code}: допустимый диапазон "
				f"от {definition.min_value} до {definition.max_value}"
			)

		context[f"attribute.{code}"] = value

	derived: dict[str, int] = {}
	steps: list[CalculationStep] = []

	for code in config.calculation_order():
		value = evaluate_formula(
			formula=config.derived[code].formula,
			context=context,
			steps=steps,
			code=f"stat.{code}",
		)

		derived[code] = value
		context[f"stat.{code}"] = value

	return AttributePreviewResult(
		attributes=dict(data.attributes),
		derived=derived,
		steps=steps,
	)