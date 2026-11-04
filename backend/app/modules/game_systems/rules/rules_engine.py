# backend/app/modules/game_systems/rules/rules_engine.py

"""Общие операции с числовым состоянием игрового листа.

Без БД, HTTP, случайных бросков и правил конкретной системы.
Все вычисления выполняются по явно переданному профилю.
"""

from __future__ import annotations
from backend.app.modules.game_systems.rules.attribute_engine import (evaluate_attributes)
from backend.app.modules.game_systems.schemas.game_rules import (RulesProfile, SheetState, SheetStateChanges)
from backend.app.modules.game_systems.schemas.rules.rule_calculations import (AttributePreviewInput, AttributePreviewResult)
from backend.app.modules.game_systems.rules.resource_validation import initial_resource_values, resolve_resource_maxima
from backend.app.modules.game_systems.schemas.rules.rule_resources import ResourceDefinitions


def _evaluate(profile: RulesProfile, state: SheetState) -> AttributePreviewResult:
	"""Проверить соответствие состояния профилю и вычислить результат."""
	data = AttributePreviewInput(
		calculations=profile.calculations,
		attributes=dict(state.attributes),
	)

	return evaluate_attributes(data)

def validate_rules_profile(profile: RulesProfile) -> RulesProfile:
	"""Проверить структуру и вычислимость начального профиля.

    Проверяются начальные числовые значения, максимумы ресурсов
    и допустимость их начального заполнения.

    Это не доказательство вычислимости для всех будущих состояний.
    """

	profile = RulesProfile.model_validate(profile)

	initial_state = SheetState(attributes=dict(profile.initial_attributes))
	result = _evaluate(profile, initial_state)

	definitions = ResourceDefinitions(resources=profile.resources)
	limits = resolve_resource_maxima(definitions, result)

	initial_resource_values(definitions, limits)

	return profile

def create_sheet_state(profile: RulesProfile, changes: SheetStateChanges | None = None) -> SheetState:
	"""Создать новое состояние из явно настроенных начальных значений.

	changes позволяет заменить часть начальных значений.
	Производные показатели от вызывающего кода не принимаются.
	"""
	profile = validate_rules_profile(profile)

	attributes = dict(profile.initial_attributes)

	if changes is not None:
		changes = SheetStateChanges.model_validate(changes)

		unknown = sorted(
			set(changes.attributes)
			- set(profile.calculations.attributes)
		)

		if unknown:
			raise ValueError(
				"Неизвестные показатели: "
				+ ", ".join(unknown)
			)

		attributes.update(changes.attributes)

	state = SheetState(attributes=attributes)

	# Проверяем диапазоны и вычислимость полученного состояния.
	_evaluate(profile, state)

	return state

def evaluate_sheet_state(profile: RulesProfile, state: SheetState) -> AttributePreviewResult:
	"""Вычислить производные показатели без изменения состояния."""
	profile = RulesProfile.model_validate(profile)
	state = SheetState.model_validate(state)

	return _evaluate(profile, state)

def apply_sheet_changes(profile: RulesProfile, state: SheetState, changes: SheetStateChanges) -> SheetState:
	"""Проверить замену значений и вернуть новое состояние.

	Переданный state не изменяется.
	Функция не проверяет права пользователя и не сохраняет данные.
	"""
	profile = RulesProfile.model_validate(profile)
	state = SheetState.model_validate(state)
	changes = SheetStateChanges.model_validate(changes)

	# Повреждённое или несовместимое исходное состояние
	# нельзя незаметно исправлять частичным обновлением.
	_evaluate(profile, state)

	unknown = sorted(
		set(changes.attributes)
		- set(profile.calculations.attributes)
	)

	if unknown:
		raise ValueError(
			"Неизвестные показатели: "
			+ ", ".join(unknown)
		)

	attributes = dict(state.attributes)
	attributes.update(changes.attributes)

	updated = SheetState(attributes=attributes)

	# При ошибке старое состояние остаётся неизменным.
	_evaluate(profile, updated)

	return updated

__all__ = [
	"validate_rules_profile",
	"create_sheet_state",
	"evaluate_sheet_state",
	"apply_sheet_changes",
]