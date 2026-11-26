# backend/app/modules/game_systems/rules/mechanic_codec.py

"""Двустороннее преобразование между профилем правил и механикой.

Старый формат — единый ``RulesProfile`` (schema_version 3/4), где
текстовые главы лежат в разделе ``rulebook``, а числовая механика —
в ``calculations``/``initial_attributes``/``resources``.

Новый формат разделяет их:
- ``SystemMechanicContent`` (schema_version 1) — только числовая
  механика без текстового раздела;
- ``SystemTextContent`` (schema_version 1) — только главы правил.

Серверный исполнитель формул по-прежнему принимает ``RulesProfile``.
Модуль не обращается к БД и не проверяет права.
"""

from __future__ import annotations
from typing import Any

# Числовые разделы механики (без текстового раздела rulebook).
_MECHANIC_KEYS = ("calculations", "initial_attributes", "resources")


def profile_to_mechanic(profile: dict[str, Any]) -> dict[str, Any]:
    """Собрать снимок механики из профиля правил.

    Текстовый раздел ``rulebook`` отбрасывается, ``schema_version``
    приводится к формату механики (1).
    """
    if not isinstance(profile, dict):
        raise ValueError("Профиль правил должен быть объектом")

    mechanic: dict[str, Any] = {"schema_version": 1}

    for key in _MECHANIC_KEYS:
        if key in profile:
            mechanic[key] = profile[key]

    # Механика всегда хранит раздел ресурсов явно (пустой, если не задан).
    mechanic.setdefault("resources", {})

    return mechanic


def profile_to_text(profile: dict[str, Any]) -> dict[str, Any]:
    """Собрать снимок текстовых правил из профиля правил.

    Берётся только раздел ``rulebook``; числовая механика отбрасывается.
    """
    if not isinstance(profile, dict):
        raise ValueError("Профиль правил должен быть объектом")

    rulebook = profile.get("rulebook")

    return {
        "schema_version": 1,
        "chapters": dict(rulebook) if isinstance(rulebook, dict) else {},
    }


def mechanic_to_profile(mechanic: dict[str, Any]) -> dict[str, Any]:
    """Собрать профиль правил из снимка механики.

    Результат готов к передаче серверному исполнителю формул:
    ``schema_version`` приводится к 4, текстовый раздел пуст.
    """
    if not isinstance(mechanic, dict):
        raise ValueError("Механика должна быть объектом")

    profile: dict[str, Any] = {"schema_version": 4, "rulebook": {}}

    for key in _MECHANIC_KEYS:
        if key in mechanic:
            profile[key] = mechanic[key]

    # Профиль версии 4 требует явного раздела ресурсов.
    profile.setdefault("resources", {})

    return profile


def split_overrides(overrides: dict[str, Any] | None) -> dict[str, Any] | None:
    """Оставить в переопределениях только числовые разделы механики.

    Текст (``rulebook``) из переопределений механики исключается.
    Пустой результат нормализуется в пустой объект, а не в ``None``,
    чтобы согласованность пары (основа, переопределения) не нарушалась.
    """
    if not isinstance(overrides, dict):
        return None

    numeric = {key: overrides[key] for key in _MECHANIC_KEYS if key in overrides}

    return numeric
