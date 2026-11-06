# backend/app/modules/game_systems/services/system_rule_origin.py

"""Загрузка основы и проверка происхождения правил.

Не выполняет commit или rollback.
Не проверяет право управлять игровой системой.

Вызывающий сервис обязан:
- проверить право управления системой;
- обеспечить чистую сессию для операции;
- заблокировать систему, затем её черновик;
- проверить ожидаемую ревизию;
- завершить транзакцию во внешнем слое.

Здесь проверяется доступность нового выбора основы,
но не заменяется авторизация самой игровой системы.
"""

from __future__ import annotations
from collections.abc import Mapping
from typing import Any
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.modules.game_systems.errors import (GameSystemNotFound, GameSystemRulesConflict, InvalidGameSystemRules)
from backend.app.modules.game_systems.models.rule_engines import (RuleEngine, RuleEngineVersion)
from backend.app.modules.game_systems.rules.rules_composition import compose_system_draft, compose_system_rules
from backend.app.modules.game_systems.rules.rules_engine import (validate_rules_profile)
from backend.app.modules.game_systems.schemas.game_rules import (RulesProfile)
from backend.app.modules.game_systems.schemas.game_system_origin import (EngineRulesSource)


_ENGINES = RuleEngine.__table__
_VERSIONS = RuleEngineVersion.__table__


def _require_actor(actor_id: UUID) -> None:
	"""Не принимать отсутствующего или некорректного участника."""
	if not isinstance(actor_id, UUID):
		raise InvalidGameSystemRules(
			"Для выбора основы требуется идентификатор пользователя"
		)

def _saved_origin(draft: Mapping[str, Any]) -> tuple[UUID | None, dict[str, Any] | None]:
	"""Проверить согласованность пары полей происхождения."""
	version_id = draft["engine_version_id"]
	overrides = draft["rules_overrides_json"]

	if version_id is None and overrides is None:
		return None, None

	if (
			not isinstance(version_id, UUID)
			or not isinstance(overrides, dict)
	):
		raise GameSystemRulesConflict(
			"Нарушена согласованность происхождения правил"
		)

	return version_id, overrides

def _assemble(version: Mapping[str, Any], overrides: dict[str, Any], executor_version: str, *, stored: bool, draft_mode: bool = False) -> dict[str, Any]:
	"""Собрать снимок с нормализованными переопределениями."""
	if version["rules_engine_version"] != executor_version:
		raise GameSystemRulesConflict(
			"Версии программного исполнителя основы "
			"и игровой системы не совпадают"
		)

	try:
		base = RulesProfile.model_validate(
			version["rules_json"]
		)
		base = validate_rules_profile(base)
	except ValueError as exc:
		raise GameSystemRulesConflict(
			"Опубликованная основа не проходит проверку правил"
		) from exc

	try:
		composer = compose_system_draft if draft_mode else compose_system_rules
		effective = composer(base, overrides)
	except ValueError as exc:
		if stored:
			raise GameSystemRulesConflict(
				"Сохранённые переопределения "
				"не позволяют собрать профиль"
			) from exc

		raise InvalidGameSystemRules(
			"Переданные переопределения "
			"не позволяют собрать профиль"
		) from exc

	payload = effective.model_dump(mode="json")

	return {
		"engine_version_id": version["id"],
		"rules_overrides_json": {
			key: payload[key]
			for key in overrides
		},
		"rules_json": payload,
	}

async def load_engine_origin(session: AsyncSession, source: EngineRulesSource, actor_id: UUID, executor_version: str) -> dict[str, Any]:
	"""Загрузить доступную публикацию при новом выборе основы."""
	_require_actor(actor_id)

	source = EngineRulesSource.model_validate(
		source.model_dump(mode="python")
	)

	result = await session.execute(
		select(
			_VERSIONS.c.id,
			_VERSIONS.c.engine_id,
			_VERSIONS.c.rules_json,
			_VERSIONS.c.rules_engine_version,
			_ENGINES.c.owner_id,
			_ENGINES.c.visibility,
			_ENGINES.c.is_active,
		)
		.select_from(
			_VERSIONS.join(
				_ENGINES,
				_ENGINES.c.id == _VERSIONS.c.engine_id,
				)
		)
		.where(
			_VERSIONS.c.id == source.engine_version_id,
			_VERSIONS.c.engine_id == source.engine_id,
			)
		.with_for_update(
			read=True,
			of=_ENGINES,
		)
	)
	version = result.mappings().one_or_none()

	if version is None:
		raise GameSystemNotFound(
			"Доступная публикация основы не найдена"
		)

	is_owner = version["owner_id"] == actor_id
	is_public = version["visibility"] == "public"

	if (
			not version["is_active"]
			or not (is_owner or is_public)
	):
		raise GameSystemNotFound(
			"Доступная публикация основы не найдена"
		)

	return _assemble(
		version,
		source.rules_overrides,
		executor_version,
		stored=False,
		draft_mode=True,
	)

async def load_saved_engine_version(session: AsyncSession, draft: Mapping[str, Any]) -> Mapping[str, Any]:
	"""Прочитать основу уже сохранённого связанного черновика.

	Активность и видимость карточки повторно не проверяются:
	это не новый выбор основы.
	"""
	version_id, _ = _saved_origin(draft)

	if version_id is None:
		raise GameSystemNotFound(
			"Черновик использует самостоятельные правила"
		)

	result = await session.execute(
		select(_VERSIONS).where(
			_VERSIONS.c.id == version_id,
			)
	)
	version = result.mappings().one_or_none()

	if version is None:
		raise GameSystemRulesConflict(
			"Сохранённая публикация основы не найдена"
		)

	return version

async def load_editor_engine_origin(session: AsyncSession, source: EngineRulesSource, actor_id: UUID,
    executor_version: str, current_draft: Mapping[str, Any] | None) -> dict[str, Any]:
	"""Собрать профиль при сохранении выбора в редакторе.

	Для той же публикации сохраняем существующую связь.
	Для другой — заново проверяем доступность основы.
	"""
	_require_actor(actor_id)

	source = EngineRulesSource.model_validate(
		source.model_dump(mode="python")
	)

	if current_draft is not None:
		saved_version_id, _ = _saved_origin(
			current_draft
		)

		if saved_version_id == source.engine_version_id:
			version = await load_saved_engine_version(
				session,
				current_draft,
			)

			if version["engine_id"] != source.engine_id:
				raise GameSystemNotFound(
					"Публикация выбранной основы не найдена"
				)

			return _assemble(
				version,
				source.rules_overrides,
				executor_version,
				stored=False,
				draft_mode=True,
			)

	return await load_engine_origin(
		session,
		source,
		actor_id,
		executor_version,
	)

async def origin_for_publication(session: AsyncSession, draft: Mapping[str, Any], executor_version: str, payload: dict[str, Any]) -> dict[str, Any]:
	"""Сверить сохранённый снимок с основой и переопределениями."""
	version_id, overrides = _saved_origin(draft)

	if version_id is None:
		# Не передаём None в JSONB:
		# самостоятельное происхождение представляется SQL NULL.
		return {}

	version = await load_saved_engine_version(
		session,
		draft,
	)

	assembled = _assemble(
		version,
		overrides,
		executor_version,
		stored=True,
	)

	if assembled["rules_json"] != payload:
		raise GameSystemRulesConflict(
			"Сохранённый профиль не совпадает "
			"с основой и переопределениями"
		)

	return {
		"engine_version_id": assembled["engine_version_id"],
		"rules_overrides_json": assembled["rules_overrides_json"],
	}