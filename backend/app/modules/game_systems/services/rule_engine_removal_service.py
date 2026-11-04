# backend/app/modules/game_systems/services/rule_engine_removal_service.py

"""Чтение плана операции над собственной основой правил.

Административное разрешение проверяет HTTP-адаптер.
actor_id поступает только из проверенной аутентификации.

Снимок читается одним PostgreSQL SELECT. Запрос сохраняет исходные
имена таблиц и использует настроенный search_path подключения.

В снимок входят все правила связанных систем, а не только правила,
непосредственно ссылающиеся на выбранную основу.

Сервис не изменяет данные, не блокирует граф зависимостей
и не выполняет commit или rollback.

Контрольный отпечаток обнаруживает изменение включённых в снимок
данных, но не заменяет проверку дополнительных зависимостей.
Исполнение удаления в этом модуле пока не подключено.
"""

from __future__ import annotations
import hashlib
import json
from typing import Any
from uuid import UUID
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.modules.game_systems.errors import GameSystemNotFound, GameSystemRulesStorageError, InvalidGameSystemRules
from backend.app.modules.game_systems.schemas.rules.rule_engine_removal import RuleEngineRemovalPlan


_SNAPSHOT_SQL = text("""
    WITH selected_engine AS (
        SELECT *
        FROM rule_engines
        WHERE id = :engine_id
          AND owner_id = :actor_id
    ),
    engine_versions AS (
        SELECT v.*
        FROM rule_engine_versions AS v
        JOIN selected_engine AS e ON e.id = v.engine_id
    ),
    origin_systems AS (
        SELECT d.system_id
        FROM game_system_rules_drafts AS d
        JOIN engine_versions AS v ON v.id = d.engine_version_id

        UNION

        SELECT r.system_id
        FROM game_system_rules_versions AS r
        JOIN engine_versions AS v ON v.id = r.engine_version_id
    ),
    linked_systems AS (
        SELECT s.*
        FROM game_systems AS s
        JOIN origin_systems AS o ON o.system_id = s.id
    ),
    linked_games AS (
        SELECT g.*
        FROM games AS g
        JOIN linked_systems AS s ON s.id = g.system_id
    ),
    linked_sessions AS (
        SELECT s.*
        FROM sessions AS s
        JOIN linked_games AS g ON g.id = s.game_id
    )
    SELECT jsonb_build_object(
        'engine',
        (SELECT to_jsonb(e) FROM selected_engine AS e),

        'engine_drafts',
        COALESCE((
            SELECT jsonb_agg(to_jsonb(d) ORDER BY d.id)
            FROM rule_engine_drafts AS d
            JOIN selected_engine AS e ON e.id = d.engine_id
        ), '[]'::jsonb),

        'engine_versions',
        COALESCE((
            SELECT jsonb_agg(to_jsonb(v) ORDER BY v.id)
            FROM engine_versions AS v
        ), '[]'::jsonb),

        'systems',
        COALESCE((
            SELECT jsonb_agg(to_jsonb(s) ORDER BY s.id)
            FROM linked_systems AS s
        ), '[]'::jsonb),

        'system_drafts',
        COALESCE((
            SELECT jsonb_agg(to_jsonb(d) ORDER BY d.id)
            FROM game_system_rules_drafts AS d
            JOIN linked_systems AS s ON s.id = d.system_id
        ), '[]'::jsonb),

        'system_versions',
        COALESCE((
            SELECT jsonb_agg(to_jsonb(v) ORDER BY v.id)
            FROM game_system_rules_versions AS v
            JOIN linked_systems AS s ON s.id = v.system_id
        ), '[]'::jsonb),

        'games',
        COALESCE((
            SELECT jsonb_agg(to_jsonb(g) ORDER BY g.id)
            FROM linked_games AS g
        ), '[]'::jsonb),

        'sessions',
        COALESCE((
            SELECT jsonb_agg(to_jsonb(s) ORDER BY s.id)
            FROM linked_sessions AS s
        ), '[]'::jsonb)
    )
""")

_COLLECTIONS = (
	"engine_drafts",
	"engine_versions",
	"systems",
	"system_drafts",
	"system_versions",
	"games",
	"sessions",
)

def _prepare(session: AsyncSession, engine_id: UUID, actor_id: UUID) -> None:
	if not isinstance(actor_id, UUID):
		raise InvalidGameSystemRules("Требуется идентификатор проверенного пользователя")

	if not isinstance(engine_id, UUID):
		raise InvalidGameSystemRules("Требуется идентификатор основы правил")

	if session.new or session.dirty or session.deleted:
		raise RuntimeError("План операции требует сессии без ожидающих ORM-изменений")

def _token(snapshot: dict[str, Any]) -> str:
	"""Сохранить алгоритм отпечатка исходного сервиса."""
	payload = json.dumps(snapshot, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
	return hashlib.sha256(payload.encode("utf-8")).hexdigest()

def _action(snapshot: dict[str, Any]) -> str:
	if snapshot["sessions"]:
		return "deactivate"

	if any(game["master_id"] is None for game in snapshot["games"]):
		return "blocked"

	return "delete"

async def _read_snapshot(session: AsyncSession, engine_id: UUID, actor_id: UUID) -> dict[str, Any]:
	result = await session.execute(_SNAPSHOT_SQL, {"engine_id": engine_id, "actor_id": actor_id})
	snapshot = result.scalar_one()

	try:
		if not isinstance(snapshot, dict):
			raise ValueError("Snapshot must be an object")

		engine = snapshot["engine"]

		if engine is None:
			raise GameSystemNotFound("Основа правил не найдена")

		if not isinstance(engine, dict):
			raise ValueError("Engine must be an object")

		if UUID(engine["id"]) != engine_id or UUID(engine["owner_id"]) != actor_id:
			raise ValueError("Unexpected engine identity")

		for name in _COLLECTIONS:
			rows = snapshot[name]

			if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
				raise ValueError("Snapshot collection must contain objects")

		if any("master_id" not in game for game in snapshot["games"]):
			raise ValueError("Game owner field is missing")

	except (ValueError, TypeError, KeyError, AttributeError) as exc:
		raise GameSystemRulesStorageError("Снимок зависимостей основы имеет неподдерживаемый формат") from exc

	return snapshot

async def get_removal_plan(session: AsyncSession, engine_id: UUID, actor_id: UUID) -> RuleEngineRemovalPlan:
	"""Прочитать план собственной основы без выполнения операции."""
	_prepare(session, engine_id, actor_id)
	snapshot = await _read_snapshot(session, engine_id, actor_id)

	try:
		return RuleEngineRemovalPlan(
			engine_id=engine_id,
			engine_name=snapshot["engine"]["name"],
			versions_count=len(snapshot["engine_versions"]),
			systems_count=len(snapshot["systems"]),
			games_count=len(snapshot["games"]),
			sessions_count=len(snapshot["sessions"]),
			unowned_games_count=sum(game["master_id"] is None for game in snapshot["games"]),
			proposed_action=_action(snapshot),
			snapshot_token=_token(snapshot),
		)
	except (ValueError, TypeError, KeyError) as exc:
		raise GameSystemRulesStorageError("Не удалось сформировать план операции над основой") from exc