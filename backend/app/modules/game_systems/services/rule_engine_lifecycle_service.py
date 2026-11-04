# backend/app/modules/game_systems/services/rule_engine_lifecycle_service.py

"""Предварительный анализ известных зависимостей основы правил.

Доступен только владельцу основы. actor_id поступает из аутентификации.
Административное разрешение проверяет вызывающий HTTP-адаптер.

Сервис выполняет один SELECT, не изменяет данные и не управляет
транзакцией. Все счётчики относятся к одному SQL-оператору.

В PostgreSQL запрос использует согласованный снимок своего выполнения.
Он не блокирует граф зависимостей и не гарантирует сохранность снимка
после завершения запроса.

Предлагаемое действие не разрешает удаление и не заменяет полный план.
Произвольные внешние ключи и содержимое файлов здесь не анализируются.
"""

from __future__ import annotations
from uuid import UUID
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import FromClause, Select
from backend.app.modules.game_systems.errors import GameSystemNotFound, GameSystemRulesStorageError, InvalidGameSystemRules
from backend.app.modules.game_systems.models.game_systems import GameSystem, GameSystemRulesDraft, GameSystemRulesVersion
from backend.app.modules.game_systems.models.rule_engines import RuleEngine, RuleEngineVersion
from backend.app.modules.game_systems.schemas.rules.rule_engine_lifecycle import RuleEngineRemovalPreview
from backend.app.modules.games.models.lobby import Game, Session as GameSession


_ENGINES = RuleEngine.__table__
_ENGINE_VERSIONS = RuleEngineVersion.__table__
_SYSTEMS = GameSystem.__table__
_SYSTEM_DRAFTS = GameSystemRulesDraft.__table__
_SYSTEM_VERSIONS = GameSystemRulesVersion.__table__
_GAMES = Game.__table__
_SESSIONS = GameSession.__table__

def _prepare(session: AsyncSession, engine_id: UUID, actor_id: UUID) -> None:
	"""Отклонить некорректные идентификаторы и посторонние ORM-изменения."""
	if not isinstance(actor_id, UUID):
		raise InvalidGameSystemRules("Требуется идентификатор проверенного пользователя")

	if not isinstance(engine_id, UUID):
		raise InvalidGameSystemRules("Требуется идентификатор основы правил")

	if session.new or session.dirty or session.deleted:
		raise RuntimeError("Анализ основы требует сессии без ожидающих ORM-изменений")

def _count_rows(source: FromClause):
	return select(func.count()).select_from(source).scalar_subquery()

def _preview_statement(engine_id: UUID, actor_id: UUID) -> Select:
	engine_versions = (
		select(_ENGINE_VERSIONS.c.id)
		.where(_ENGINE_VERSIONS.c.engine_id == engine_id)
		.cte("removal_engine_versions")
	)

	draft_systems = (
		select(_SYSTEM_DRAFTS.c.system_id)
		.select_from(
			_SYSTEM_DRAFTS.join(
				engine_versions,
				_SYSTEM_DRAFTS.c.engine_version_id == engine_versions.c.id,
				)
		)
	)
	published_systems = (
		select(_SYSTEM_VERSIONS.c.system_id)
		.select_from(
			_SYSTEM_VERSIONS.join(
				engine_versions,
				_SYSTEM_VERSIONS.c.engine_version_id == engine_versions.c.id,
				)
		)
	)

	# UNION устраняет повторы между черновиками и публикациями,
	# а также между несколькими публикациями одной системы.
	origin_systems = draft_systems.union(published_systems).cte("removal_origin_systems")

	linked_systems = (
		select(_SYSTEMS.c.id)
		.where(_SYSTEMS.c.id.in_(select(origin_systems.c.system_id)))
		.cte("removal_linked_systems")
	)
	linked_games = (
		select(_GAMES.c.id, _GAMES.c.master_id)
		.where(_GAMES.c.system_id.in_(select(linked_systems.c.id)))
		.cte("removal_linked_games")
	)

	# Учитываются все сохранённые встречи, включая завершённые.
	linked_sessions = (
		select(_SESSIONS.c.id)
		.where(_SESSIONS.c.game_id.in_(select(linked_games.c.id)))
		.cte("removal_linked_sessions")
	)
	unowned_count = (
		select(func.count())
		.select_from(linked_games)
		.where(linked_games.c.master_id.is_(None))
		.scalar_subquery()
	)

	return (
		select(
			_ENGINES.c.id.label("engine_id"),
			_ENGINES.c.name.label("engine_name"),
			_count_rows(engine_versions).label("versions_count"),
			_count_rows(linked_systems).label("systems_count"),
			_count_rows(linked_games).label("games_count"),
			_count_rows(linked_sessions).label("sessions_count"),
			unowned_count.label("unowned_games_count"),
		)
		.where(
			_ENGINES.c.id == engine_id,
			_ENGINES.c.owner_id == actor_id,
			)
	)

async def preview_engine_removal(session: AsyncSession, engine_id: UUID, actor_id: UUID) -> RuleEngineRemovalPreview:
	"""Прочитать известные зависимости собственной основы без изменений."""
	_prepare(session, engine_id, actor_id)

	result = await session.execute(_preview_statement(engine_id, actor_id))
	row = result.mappings().one_or_none()

	if row is None:
		raise GameSystemNotFound("Основа правил не найдена")

	try:
		if row["sessions_count"] > 0:
			action = "deactivate"
		elif row["unowned_games_count"] > 0:
			action = "blocked"
		else:
			action = "delete"

		return RuleEngineRemovalPreview.model_validate({
			**dict(row),
			"proposed_action": action,
		})
	except (ValueError, TypeError, KeyError) as exc:
		raise GameSystemRulesStorageError("Результат анализа зависимостей основы имеет неподдерживаемый формат") from exc