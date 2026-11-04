# backend/app/modules/game_systems/schemas/rules/rule_calculations.py

"""Контракты общих целочисленных вычислений.

Названия показателей и формулы задаются данными.
Модуль не содержит правил конкретной игровой системы.
"""

from __future__ import annotations
from collections.abc import Iterator
import re
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


# Технические ограничения исполнителя, а не игровые правила.
VALUE_LIMIT = 1_000_000_000
MAX_FORMULA_DEPTH = 8
MAX_FORMULA_NODES = 256
MAX_FORMULA_ARGUMENTS = 16
MAX_ATTRIBUTES = 128
MAX_DERIVED_STATS = 128

_CODE_PATTERN = r"^[a-z][a-z0-9_]{0,39}$"
_REFERENCE_PATTERN = r"^(attribute|stat)\.[a-z][a-z0-9_]{0,39}$"

Code = Annotated[str, Field(pattern=_CODE_PATTERN)]
CalculationValue = Annotated[
	int,
	Field(ge=-VALUE_LIMIT, le=VALUE_LIMIT),
]

CalculationOperation = Literal[
	"sum",
	"subtract",
	"multiply",
	"floor_div",
	"ceil_div",
	"min",
	"max",
]


class CalculationModel(BaseModel):
	model_config = ConfigDict(
		extra="forbid",
		strict=True,
		validate_default=True,
		revalidate_instances="always",
	)

class StatFormula(CalculationModel):
	"""Дерево разрешённых операций, чисел и ссылок."""

	operation: CalculationOperation
	arguments: list[int | str | StatFormula] = Field(
		min_length=1,
		max_length=MAX_FORMULA_ARGUMENTS,
	)

	@model_validator(mode="before")
	@classmethod
	def validate_complexity(cls, raw):
		stack = [(raw, 1)]
		nodes = 0

		while stack:
			current, depth = stack.pop()
			nodes += 1

			if nodes > MAX_FORMULA_NODES:
				raise ValueError(
					"Формула содержит слишком много элементов"
				)

			if isinstance(current, cls):
				arguments = current.arguments
			elif isinstance(current, dict):
				arguments = current.get("arguments")
			else:
				continue

			if depth > MAX_FORMULA_DEPTH:
				raise ValueError(
					"Превышена допустимая глубина формулы"
				)

			if isinstance(arguments, list):
				if not 1 <= len(arguments) <= MAX_FORMULA_ARGUMENTS:
					raise ValueError(
						"Недопустимое количество аргументов операции"
					)

				stack.extend(
					(argument, depth + 1)
					for argument in arguments
				)

		return raw

	@model_validator(mode="after")
	def validate_arguments(self):
		binary_operations = {
			"subtract",
			"floor_div",
			"ceil_div",
		}

		if (
				self.operation in binary_operations
				and len(self.arguments) != 2
		):
			raise ValueError(
				"Вычитание и деление требуют ровно два аргумента"
			)

		for argument in self.arguments:
			if isinstance(argument, StatFormula):
				continue

			if type(argument) is int:
				if abs(argument) > VALUE_LIMIT:
					raise ValueError(
						"Константа выходит за технический диапазон"
					)
				continue

			if not re.fullmatch(_REFERENCE_PATTERN, argument):
				raise ValueError(
					f"Недопустимая ссылка: {argument}"
				)

		if self.operation in {"floor_div", "ceil_div"}:
			denominator = self.arguments[1]

			if type(denominator) is int and denominator == 0:
				raise ValueError("Деление на ноль")

		return self

	def iter_leaf_arguments(self) -> Iterator[int | str]:
		"""Обойти числа и ссылки во всех вложенных операциях."""
		stack = list(reversed(self.arguments))

		while stack:
			argument = stack.pop()

			if isinstance(argument, StatFormula):
				stack.extend(reversed(argument.arguments))
			else:
				yield argument

class AttributeChoice(CalculationModel):
	"""Подписанный целочисленный вариант исходного показателя."""

	value: CalculationValue

	label: str = Field(
		min_length=1,
		max_length=100,
		pattern=r"\S",
	)

class AttributeDefinition(CalculationModel):
	"""Исходное целое число или выбор из подписанных значений.

    Значение остаётся числом для использования в формулах.
    choices ограничивает допустимые значения, а не только
    определяет оформление поля.
    """

	label: str = Field(
		min_length=1,
		max_length=100,
		pattern=r"\S",
	)

	field_type: Literal["integer", "choice"] = "integer"

	min_value: CalculationValue = -VALUE_LIMIT
	max_value: CalculationValue = VALUE_LIMIT

	choices: list[AttributeChoice] = Field(
		default_factory=list,
		max_length=128,
	)

	@model_validator(mode="after")
	def validate_definition(self):
		if self.min_value > self.max_value:
			raise ValueError(
				"Минимальное значение превышает максимальное"
			)

		if self.field_type == "integer":
			if self.choices:
				raise ValueError(
					"Для числового поля варианты не задаются"
				)
			return self

		if not self.choices:
			raise ValueError(
				"Для поля выбора нужен хотя бы один вариант"
			)

		values = [item.value for item in self.choices]

		if len(values) != len(set(values)):
			raise ValueError(
				"Числовые значения вариантов не должны повторяться"
			)

		# Границы сохраняются для совместимости числового
		# исполнителя, но не заменяют проверку принадлежности.
		if (
				self.min_value != min(values)
				or self.max_value != max(values)
		):
			raise ValueError(
				"Границы поля выбора должны совпадать "
				"с минимальным и максимальным значениями вариантов"
			)

		return self

	def validate_value(self, value: int) -> int:
		"""Проверить конкретное значение относительно определения."""

		if type(value) is not int:
			raise ValueError("Требуется целое число")

		if not self.min_value <= value <= self.max_value:
			raise ValueError(
				f"Допустимый диапазон: "
				f"от {self.min_value} до {self.max_value}"
			)

		if self.field_type == "choice":
			allowed = {item.value for item in self.choices}

			if value not in allowed:
				raise ValueError(
					"Значение отсутствует среди разрешённых вариантов"
				)

		return value

class DerivedStat(CalculationModel):
	"""Показатель, который вычисляется, а не принимается от клиента."""

	label: str = Field(
		min_length=1,
		max_length=100,
		pattern=r"\S",
	)
	formula: StatFormula

class AttributeCalculations(CalculationModel):
	attributes: dict[Code, AttributeDefinition] = Field(
		default_factory=dict,
		max_length=MAX_ATTRIBUTES,
	)
	derived: dict[Code, DerivedStat] = Field(
		default_factory=dict,
		max_length=MAX_DERIVED_STATS,
	)

	def calculation_order(self) -> list[str]:
		"""Проверить ссылки и построить порядок вычислений."""
		dependencies: dict[str, set[str]] = {}

		for code, definition in self.derived.items():
			required: set[str] = set()

			for argument in definition.formula.iter_leaf_arguments():
				if type(argument) is int:
					continue

				namespace, target = argument.split(".", 1)

				if namespace == "attribute":
					if target not in self.attributes:
						raise ValueError(
							f"Показатель {code}: "
							f"неизвестный исходный показатель {target}"
						)
				else:
					if target not in self.derived:
						raise ValueError(
							f"Показатель {code}: "
							f"неизвестный вычисляемый показатель {target}"
						)
					required.add(target)

			dependencies[code] = required

		order: list[str] = []

		while dependencies:
			ready = sorted(
				code
				for code, required in dependencies.items()
				if not required
			)

			if not ready:
				unresolved = ", ".join(sorted(dependencies))
				raise ValueError(
					"Обнаружен цикл зависимостей; "
					f"не удалось упорядочить показатели: {unresolved}"
				)

			order.extend(ready)

			for code in ready:
				del dependencies[code]

			for required in dependencies.values():
				required.difference_update(ready)

		return order

	@model_validator(mode="after")
	def validate_graph(self):
		self.calculation_order()
		return self

class CalculationStep(CalculationModel):
	code: str
	operation: CalculationOperation
	arguments: list[int | str | StatFormula]
	resolved_arguments: list[CalculationValue]
	value: CalculationValue

class AttributePreviewInput(CalculationModel):
	calculations: AttributeCalculations

	attributes: dict[Code, CalculationValue] = Field(
		default_factory=dict,
		max_length=MAX_ATTRIBUTES,
	)

	@model_validator(mode="after")
	def validate_attribute_values(self):
		definitions = self.calculations.attributes

		for code, value in self.attributes.items():
			definition = definitions.get(code)

			if definition is None:
				raise ValueError(
					f"Неизвестный исходный показатель: {code}"
				)

			try:
				definition.validate_value(value)
			except ValueError as error:
				raise ValueError(
					f"Показатель {code}: {error}"
				) from error

		return self

class AttributePreviewResult(CalculationModel):
	attributes: dict[Code, CalculationValue]
	derived: dict[Code, CalculationValue]
	steps: list[CalculationStep]

StatFormula.model_rebuild()