# backend/app/modules/game_systems/rules/formula_engine.py

"""Исполнитель разрешённых целочисленных операций."""

from __future__ import annotations
from collections.abc import Mapping
from backend.app.modules.game_systems.schemas.rule_calculations import (CalculationStep, MAX_FORMULA_ARGUMENTS, StatFormula, VALUE_LIMIT)


def bounded(value: int) -> int:
	"""Проверить тип и технический диапазон числа."""
	if type(value) is not int:
		raise ValueError(
			"Вычисление допускает только целые числа"
		)

	if abs(value) > VALUE_LIMIT:
		raise ValueError(
			"Значение выходит за технический диапазон"
		)

	return value

def apply_operation(operation: str, values: list[int]) -> int:
	"""Выполнить одну разрешённую операцию."""
	if not 1 <= len(values) <= MAX_FORMULA_ARGUMENTS:
		raise ValueError(
			"Недопустимое количество аргументов операции"
		)

	values = [bounded(value) for value in values]

	if operation in {"subtract", "floor_div", "ceil_div"}:
		if len(values) != 2:
			raise ValueError(
				"Операция требует ровно два аргумента"
			)

	if operation == "sum":
		return bounded(sum(values))

	if operation == "subtract":
		return bounded(values[0] - values[1])

	if operation == "multiply":
		result = 1

		for value in values:
			result = bounded(result * value)

		return result

	if operation in {"floor_div", "ceil_div"}:
		numerator, denominator = values

		if denominator == 0:
			raise ValueError("Деление на ноль")

		if operation == "floor_div":
			return bounded(numerator // denominator)

		return bounded(-((-numerator) // denominator))

	if operation == "min":
		return bounded(min(values))

	if operation == "max":
		return bounded(max(values))

	raise ValueError("Неизвестная операция вычисления")

def evaluate_formula(formula: StatFormula, context: Mapping[str, int], steps: list[CalculationStep] | None = None, code: str = "formula") -> int:
	"""Вычислить проверенную формулу в явно переданном контексте.

	Не обращается к БД, файловой системе или глобальным переменным.
	steps=None отключает формирование пояснения.
	"""
	formula = StatFormula.model_validate(formula)

	def evaluate(node: StatFormula, path: str) -> int:
		resolved: list[int] = []

		for index, argument in enumerate(node.arguments):
			if isinstance(argument, StatFormula):
				value = evaluate(
					argument,
					f"{path}/{index}",
				)
			elif type(argument) is int:
				value = argument
			else:
				if argument not in context:
					raise ValueError(
						f"Вычисление {path}: "
						f"недоступный источник {argument}"
					)

				value = context[argument]

			resolved.append(bounded(value))

		try:
			value = apply_operation(
				node.operation,
				resolved,
			)
		except ValueError as exc:
			raise ValueError(
				f"Вычисление {path}: {exc}"
			) from exc

		if steps is not None:
			steps.append(
				CalculationStep(
					code=path,
					operation=node.operation,
					arguments=list(node.arguments),
					resolved_arguments=resolved,
					value=value,
				)
			)

		return value

	return evaluate(formula, code)