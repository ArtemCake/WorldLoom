# backend/app/modules/games/services/dice_engine.py

"""Ограниченный язык бросков: группы костей, выбор результатов и сложение."""

from __future__ import annotations
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass


MAX_FORMULA_LENGTH = 100
MAX_DICE_COUNT = 100
MAX_DICE_SIDES = 1000
MAX_MODIFIER_ABS = 10_000
TERM_PATTERN = re.compile(r"([+-]?)(?:([0-9]+)d([0-9]+)(?:(kh|kl)([0-9]+))?|([0-9]+))")

class InvalidDiceExpression(ValueError):
	"""Выражение не соответствует поддерживаемому языку бросков."""

@dataclass(frozen=True)
class DiceTerm:
	sign: int
	count: int = 0
	sides: int = 0
	keep: int = 0
	selection: str | None = None
	constant: int = 0

@dataclass(frozen=True)
class DiceResult:
	result_total: int
	individual_results: tuple[int, ...]

@dataclass(frozen=True)
class DiceExpression:
	formula: str
	terms: tuple[DiceTerm, ...]

	@classmethod
	def parse(cls, formula: str) -> DiceExpression:
		if not isinstance(formula, str) or not 1 <= len(formula) <= MAX_FORMULA_LENGTH:
			raise InvalidDiceExpression("Длина выражения должна быть от 1 до 100 символов")

		normalized = formula.strip().lower()
		terms = []
		position = 0
		dice_count = 0
		modifier_budget = 0

		for match in TERM_PATTERN.finditer(normalized):
			if match.start() != position or (position > 0 and not match.group(1)):
				raise InvalidDiceExpression("Недопустимый синтаксис выражения броска")

			sign_text, count_text, sides_text, selection, keep_text, constant_text = match.groups()
			sign = -1 if sign_text == "-" else 1

			if constant_text is not None:
				constant = int(constant_text)
				modifier_budget += constant

				if modifier_budget > MAX_MODIFIER_ABS:
					raise InvalidDiceExpression("Сумма абсолютных значений модификаторов превышает 10000")

				terms.append(DiceTerm(sign=sign, constant=constant))
			else:
				count = int(count_text)
				sides = int(sides_text)
				keep = int(keep_text) if keep_text is not None else count
				dice_count += count

				if not 1 <= count <= MAX_DICE_COUNT or dice_count > MAX_DICE_COUNT:
					raise InvalidDiceExpression("В одном выражении допустимо от 1 до 100 костей суммарно")

				if not 1 <= sides <= MAX_DICE_SIDES:
					raise InvalidDiceExpression("Количество граней должно быть от 1 до 1000")

				if not 1 <= keep <= count:
					raise InvalidDiceExpression("Число сохраняемых результатов должно быть от 1 до числа костей группы")

				terms.append(DiceTerm(sign=sign, count=count, sides=sides, keep=keep, selection=selection))

			position = match.end()

		if position != len(normalized) or not terms or dice_count == 0:
			raise InvalidDiceExpression("Ожидается выражение с костями, например 2d6+3 или 3d8kh2")

		return cls(formula=normalized, terms=tuple(terms))

	def roll(self, randbelow: Callable[[int], int] | None = None) -> DiceResult:
		random_number = secrets.randbelow if randbelow is None else randbelow
		individual = []
		total = 0

		for term in self.terms:
			if term.count == 0:
				total += term.sign * term.constant
				continue

			values = []

			for _ in range(term.count):
				value = random_number(term.sides)

				if type(value) is not int or not 0 <= value < term.sides:
					raise RuntimeError("Генератор случайных чисел вернул недопустимое значение")

				values.append(value + 1)

			individual.extend(values)

			if term.selection == "kh":
				selected = sorted(values, reverse=True)[:term.keep]
			elif term.selection == "kl":
				selected = sorted(values)[:term.keep]
			else:
				selected = values

			total += term.sign * sum(selected)

		return DiceResult(result_total=total, individual_results=tuple(individual))
