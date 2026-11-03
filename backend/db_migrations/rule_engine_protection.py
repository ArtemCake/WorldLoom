# backend/db_migrations/rule_engine_protection.py

"""Автоматическое добавление и обновление защиты публикаций Alembic."""

from alembic.operations import ops
from sqlalchemy import text


TABLE_NAME = "rule_engine_versions"
TRIGGER_NAME = "trg_rule_engine_versions_immutable"
FUNCTION_NAME = "worldloom_guard_rule_engine_version"

# Предыдущая известная реализация.
# Нужна для распознавания старой защиты и формирования downgrade.
LEGACY_FUNCTION_BODY = """
BEGIN
    RAISE EXCEPTION
        'Published rule engine versions are immutable'
        USING ERRCODE = '23514';
    RETURN NULL;
END;
"""

# Актуальная реализация.
#
# UPDATE остаётся запрещённым всегда.
# DELETE разрешён только для указанного движка в транзакции,
# которую подготовил административный сервис удаления.
FUNCTION_BODY = """
BEGIN
    IF TG_OP = 'DELETE'
       AND current_setting(
           'worldloom.removing_engine_id',
           true
       ) = OLD.engine_id::text
    THEN
        RETURN OLD;
    END IF;

    RAISE EXCEPTION
        'Published rule engine versions are immutable'
        USING ERRCODE = '23514';

    RETURN NULL;
END;
"""


def _create_function_sql(body):
	return (
		f"CREATE OR REPLACE FUNCTION {FUNCTION_NAME}()\n"
		"RETURNS trigger\n"
		"LANGUAGE plpgsql\n"
		"AS $$\n"
		f"{body.strip()}\n"
		"$$;\n"
	)

CREATE_FUNCTION_SQL = _create_function_sql(FUNCTION_BODY)

LEGACY_CREATE_FUNCTION_SQL = _create_function_sql(
	LEGACY_FUNCTION_BODY
)

CREATE_TRIGGER_SQL = """
CREATE TRIGGER trg_rule_engine_versions_immutable
BEFORE UPDATE OR DELETE ON rule_engine_versions
FOR EACH ROW
EXECUTE FUNCTION worldloom_guard_rule_engine_version();
"""

DROP_TRIGGER_SQL = """
DROP TRIGGER trg_rule_engine_versions_immutable
ON rule_engine_versions;
"""

DROP_FUNCTION_SQL = """
DROP FUNCTION worldloom_guard_rule_engine_version();
"""

FIND_TRIGGER_SQL = text("""
    SELECT
        t.tgenabled AS enabled_mode,
        t.tgtype AS trigger_type,
        p.proname AS function_name,
        p.pronargs AS function_arguments,
        pn.nspname = tn.nspname AS same_schema,
        p.prosrc AS function_body,
        l.lanname AS function_language
    FROM pg_trigger AS t
    JOIN pg_class AS c
        ON c.oid = t.tgrelid
    JOIN pg_namespace AS tn
        ON tn.oid = c.relnamespace
    JOIN pg_proc AS p
        ON p.oid = t.tgfoid
    JOIN pg_namespace AS pn
        ON pn.oid = p.pronamespace
    JOIN pg_language AS l
        ON l.oid = p.prolang
    WHERE t.tgrelid = to_regclass(:table_name)
      AND t.tgname = :trigger_name
      AND NOT t.tgisinternal
""")

def _normalize_body(body):
	"""Игнорировать только различия пробелов и переносов строк."""
	return " ".join(body.split())

def _migration_operations(directives):
	if len(directives) != 1:
		raise RuntimeError(
			"Автогенерация защиты ожидает один файл миграции."
		)

	script = directives[0]

	if (
			len(script.upgrade_ops_list) != 1
			or len(script.downgrade_ops_list) != 1
	):
		raise RuntimeError(
			"Автогенерация защиты ожидает одну БД."
		)

	return (
		script.upgrade_ops_list[0].ops,
		script.downgrade_ops_list[0].ops,
	)

def add_rule_engine_protection(migration_context, revision, directives):
	"""Дополнить создаваемую миграцию защитой публикаций.

	Подключается через process_revision_directives в env.py.

	Во время генерации выполняет только чтение состояния БД.
	Изменения защиты записывает в создаваемый файл миграции:
	DDL здесь не выполняется.
	"""
	if not directives:
		return

	metadata = migration_context.opts.get("target_metadata")

	if metadata is None or TABLE_NAME not in metadata.tables:
		return

	connection = migration_context.connection

	if connection is None:
		raise RuntimeError(
			"Для проверки защиты публикаций нужно подключение к БД."
		)

	if connection.dialect.name != "postgresql":
		raise RuntimeError(
			"Защита публикаций рассчитана на PostgreSQL."
		)

	trigger = connection.execute(
		FIND_TRIGGER_SQL,
		{
			"table_name": TABLE_NAME,
			"trigger_name": TRIGGER_NAME,
		},
	).mappings().one_or_none()

	if trigger is None:
		upgrade_operations, downgrade_operations = (
			_migration_operations(directives)
		)

		# В начальной миграции таблица создаётся раньше триггера.
		upgrade_operations.extend([
			ops.ExecuteSQLOp(CREATE_FUNCTION_SQL),
			ops.ExecuteSQLOp(CREATE_TRIGGER_SQL),
		])

		# При откате защита снимается до удаления таблицы.
		downgrade_operations[0:0] = [
			ops.ExecuteSQLOp(DROP_TRIGGER_SQL),
			ops.ExecuteSQLOp(DROP_FUNCTION_SQL),
		]
		return

	# PostgreSQL tgtype:
	# ROW (1) + BEFORE (2) + DELETE (8) + UPDATE (16) = 27.
	expected_trigger = (
			trigger["enabled_mode"] in {"O", "A"}
			and trigger["trigger_type"] == 27
			and trigger["function_name"] == FUNCTION_NAME
			and trigger["function_arguments"] == 0
			and trigger["same_schema"]
			and trigger["function_language"] == "plpgsql"
	)

	if not expected_trigger:
		raise RuntimeError(
			"Триггер защиты публикаций уже существует, "
			"но отключён или имеет неожиданную конфигурацию. "
			"Нужна отдельная проверка перед генерацией миграции."
		)

	actual_body = _normalize_body(trigger["function_body"])

	if actual_body == _normalize_body(FUNCTION_BODY):
		# Защита уже актуальна: лишние операции не добавляем.
		return

	if actual_body != _normalize_body(LEGACY_FUNCTION_BODY):
		# Не перезаписываем неизвестную пользовательскую реализацию.
		raise RuntimeError(
			"Обнаружена неизвестная реализация функции защиты "
			"публикаций. Автоматическое обновление остановлено; "
			"нужно проверить её содержимое."
		)

	upgrade_operations, downgrade_operations = (
		_migration_operations(directives)
	)

	# Триггер уже существует: меняем только тело его функции.
	upgrade_operations.append(
		ops.ExecuteSQLOp(CREATE_FUNCTION_SQL)
	)

	# Откат возвращает старую защиту, а не удаляет её.
	downgrade_operations.insert(
		0,
		ops.ExecuteSQLOp(LEGACY_CREATE_FUNCTION_SQL),
	)