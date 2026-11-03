# backend/app/modules/game_systems/services/delete_service.py

"""Проверка зависимостей и удаление свободной игровой системы.

Административные права проверяет вызывающий слой.
Сервис не выполняет commit, rollback или операции с файлами.

Удаление отдельной системы допускает только её черновик правил.
Проверка будущей цепочки также допускает известные связи игр
и публикаций, но сама ничего не удаляет.

Каталог PostgreSQL читается по фактическим внешним ключам.
Проверяются только прямые ссылки на таблицу игровых систем.
Логические связи без внешних ключей сюда не входят.
"""

from __future__ import annotations
from collections.abc import Mapping
from typing import Any
from uuid import UUID
from sqlalchemy import and_, column, delete, select, table, text
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.modules.game_systems.errors import GameSystemNotFound, GameSystemRulesConflict, GameSystemRulesStorageError, InvalidGameSystemRules
from backend.app.modules.game_systems.models.game_systems import GameSystem, GameSystemRulesDraft, GameSystemRulesVersion
from backend.app.modules.games.models.lobby import Game


_SYSTEMS = GameSystem.__table__
_DRAFTS = GameSystemRulesDraft.__table__
_VERSIONS = GameSystemRulesVersion.__table__
_GAMES = Game.__table__

_INCOMING_KEYS = text("""
    SELECT
        source_ns.nspname AS source_schema,
        source.relname AS source_table,
        target_ns.nspname AS target_schema,
        array_agg(
            source_column.attname ORDER BY keys.position
        ) AS source_columns,
        array_agg(
            target_column.attname ORDER BY keys.position
        ) AS target_columns
    FROM pg_constraint AS constraint_row
    JOIN pg_class AS source
        ON source.oid = constraint_row.conrelid
    JOIN pg_namespace AS source_ns
        ON source_ns.oid = source.relnamespace
    JOIN pg_class AS target
        ON target.oid = constraint_row.confrelid
    JOIN pg_namespace AS target_ns
        ON target_ns.oid = target.relnamespace
    JOIN LATERAL unnest(
        constraint_row.conkey,
        constraint_row.confkey
    ) WITH ORDINALITY AS keys(
        source_number,
        target_number,
        position
    ) ON TRUE
    JOIN pg_attribute AS source_column
        ON source_column.attrelid = source.oid
        AND source_column.attnum = keys.source_number
    JOIN pg_attribute AS target_column
        ON target_column.attrelid = target.oid
        AND target_column.attnum = keys.target_number
    WHERE constraint_row.contype = 'f'
        AND constraint_row.confrelid = CAST(:target AS regclass)
    GROUP BY
        constraint_row.oid,
        source_ns.nspname,
        source.relname,
        target_ns.nspname
    ORDER BY source_ns.nspname, source.relname, constraint_row.oid
""")

def _prepare(session: AsyncSession, system_ids: list[UUID]) -> list[UUID]:
	if not isinstance(system_ids, list) or any(not isinstance(value, UUID) for value in system_ids):
		raise InvalidGameSystemRules("Требуется список идентификаторов игровых систем")

	if session.new or session.dirty or session.deleted:
		raise RuntimeError("Операция требует сессии без ожидающих ORM-изменений")

	return sorted(set(system_ids), key=str)

def _postgresql_bind(session: AsyncSession):
	bind = session.get_bind()

	if bind.dialect.name != "postgresql":
		raise GameSystemRulesConflict("Проверка зависимостей рассчитана на PostgreSQL")

	return bind

def _reference_parts(reference: Mapping[str, Any]):
	"""Проверить описание ключа до построения динамического SELECT."""
	try:
		names = ("source_schema", "source_table", "target_schema")

		if any(not isinstance(reference[name], str) or not reference[name] for name in names):
			raise ValueError("Invalid relation identity")

		source_columns = reference["source_columns"]
		target_columns = reference["target_columns"]

		if not isinstance(source_columns, (list, tuple)) or not isinstance(target_columns, (list, tuple)):
			raise ValueError("Invalid column arrays")

		if not source_columns or len(source_columns) != len(target_columns):
			raise ValueError("Mismatched foreign key columns")

		if any(not isinstance(name, str) or not name for name in (*source_columns, *target_columns)):
			raise ValueError("Invalid column name")

		if len(set(source_columns)) != len(source_columns) or len(set(target_columns)) != len(target_columns):
			raise ValueError("Repeated foreign key column")

		if any(name not in _SYSTEMS.c for name in target_columns):
			raise ValueError("Unknown target column")

		return list(source_columns), list(target_columns)

	except (ValueError, TypeError, KeyError) as exc:
		raise GameSystemRulesStorageError("Не удалось надёжно прочитать описание внешнего ключа") from exc

def _is_handled_reference(reference: Mapping[str, Any], source_columns: list[str], target_columns: list[str], *, removal_chain: bool) -> bool:
	if source_columns != ["system_id"] or target_columns != ["id"]:
		return False

	target_schema = reference["target_schema"]

	if _SYSTEMS.schema is not None and target_schema != _SYSTEMS.schema:
		return False

	handled = (_DRAFTS, _VERSIONS, _GAMES) if removal_chain else (_DRAFTS,)

	return any(
		reference["source_schema"] == (item.schema or target_schema)
		and reference["source_table"] == item.name
		for item in handled
	)

def _reference_statement(reference: Mapping[str, Any], source_columns: list[str], target_columns: list[str], system_ids: list[UUID]):
	source = table(
		reference["source_table"],
		*[
			column(local_name, _SYSTEMS.c[target_name].type)
			for local_name, target_name in zip(source_columns, target_columns)
		],
		schema=reference["source_schema"],
	)
	conditions = [
		source.c[local_name] == _SYSTEMS.c[target_name]
		for local_name, target_name in zip(source_columns, target_columns)
	]

	return (
		select(1)
		.select_from(source.join(_SYSTEMS, and_(*conditions)))
		.where(_SYSTEMS.c.id.in_(system_ids))
		.limit(1)
	)

async def _reject_references(session: AsyncSession, system_ids: list[UUID], *, removal_chain: bool) -> None:
	bind = _postgresql_bind(session)
	target = bind.dialect.identifier_preparer.format_table(_SYSTEMS)
	result = await session.execute(_INCOMING_KEYS, {"target": target})

	for reference in result.mappings().all():
		source_columns, target_columns = _reference_parts(reference)

		if _is_handled_reference(reference, source_columns, target_columns, removal_chain=removal_chain):
			continue

		statement = _reference_statement(reference, source_columns, target_columns, system_ids)
		used = await session.execute(statement)

		if used.first() is not None:
			raise GameSystemRulesConflict(
				"У игровой системы есть связанные данные, удаление которых "
				"не предусмотрено этой операцией. Используйте деактивацию"
			)

async def assert_no_extra_system_content(session: AsyncSession, system_ids: list[UUID]) -> None:
	"""Проверить прямые зависимости перед будущим удалением цепочки.

	Эта операция не проверяет права, не блокирует системы и не является
	разрешением на удаление. Вызывающий исполнитель обязан отдельно
	проверить доступ, стабилизировать граф и обработать известные связи.
	"""
	system_ids = _prepare(session, system_ids)

	if not system_ids:
		return

	await _reject_references(session, system_ids, removal_chain=True)

async def delete_game_system(session: AsyncSession, system_id: UUID) -> dict[str, Any]:
	"""Удалить свободную систему и черновик в транзакции вызывающего слоя."""
	_prepare(session, [system_id])
	_postgresql_bind(session)

	isolation = await session.execute(text("SHOW transaction_isolation"))

	if isolation.scalar_one().lower() != "read committed":
		raise GameSystemRulesConflict("Для удаления системы требуется уровень изоляции READ COMMITTED")

	result = await session.execute(
		select(_SYSTEMS)
		.where(_SYSTEMS.c.id == system_id)
		.with_for_update()
	)
	system = result.mappings().one_or_none()

	if system is None:
		raise GameSystemNotFound("Игровая система не найдена")

	await _reject_references(session, [system_id], removal_chain=False)

	await session.execute(delete(_DRAFTS).where(_DRAFTS.c.system_id == system_id))
	deleted = await session.execute(
		delete(_SYSTEMS)
		.where(_SYSTEMS.c.id == system_id)
		.returning(_SYSTEMS.c.id)
	)

	if deleted.scalar_one_or_none() != system_id:
		raise GameSystemRulesConflict("Удаление системы не подтверждено. Получите актуальное состояние")

	return {"deleted": True, "system_id": str(system_id)}