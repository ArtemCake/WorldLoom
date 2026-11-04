# backend/app/modules/game_systems/rules/rules_composition.py

"""Композиция универсального числового профиля правил.

Не загружает данные, не проверяет права и не управляет
транзакциями.
"""

from __future__ import annotations
from copy import deepcopy
from typing import Any
from backend.app.modules.game_systems.rules.rules_engine import (validate_rules_profile)
from backend.app.modules.game_systems.schemas.game_rules import (RulesProfile)


OVERRIDABLE_FIELDS = frozenset({
	"calculations",
	"initial_attributes",
	"resources",
})

def compose_system_rules(base_rules: RulesProfile, overrides: dict[str, Any] | None = None) -> RulesProfile:
	"""Собрать независимый и проверенный итоговый профиль.

	Семантика:
	- отсутствующее поле наследуется;
	- переданное поле заменяет раздел целиком;
	- вложенные словари автоматически не объединяются;
	- None передаётся валидатору как явное значение;
	- версия схемы не переопределяется;
	- входные объекты не изменяются.
	"""
	if not isinstance(base_rules, RulesProfile):
		raise ValueError(
			"Основа должна быть профилем RulesProfile"
		)

	if overrides is None:
		overrides = {}

	if not isinstance(overrides, dict):
		raise ValueError(
			"Переопределения должны быть словарём"
		)

	if any(
			not isinstance(key, str)
			for key in overrides
	):
		raise ValueError(
			"Названия разделов должны быть строками"
		)

	forbidden = set(overrides) - OVERRIDABLE_FIELDS

	if forbidden:
		raise ValueError(
			"Недопустимые разделы переопределений: "
			+ ", ".join(sorted(forbidden))
		)

	effective = deepcopy(
		base_rules.model_dump(mode="python")
	)
	effective.update(deepcopy(overrides))

	profile = RulesProfile.model_validate(effective)

	# Проверяем не только структуру, но и вычислимость
	# итогового начального состояния.
	return validate_rules_profile(profile)
