# backend/db_migrations/system_rules_protection.py

"""SQL защиты опубликованных версий правил игровой системы.

Публикация правил обязана быть неизменяемой: её читают игры, листы
персонажей и внешние ссылки, поэтому UPDATE и TRUNCATE отклоняются на
уровне СУБД, а не только в сервисе (§17.3 «сохранить неизменяемую
публикацию», §27-G «обновление источника не меняет публикацию»).

DELETE разрешён только внутри транзакции удаления системы, которую
подготовил административный сервис. Для этого сервис устанавливает
локальный параметр ``worldloom.removing_system_id``; триггер сверяет
его с удаляемой строкой. Вне такой транзакции удаление публикации
отклоняется. Так защита не ломает легальное удаление свободной
системы (``delete_game_system``), но запрещает произвольное стирание
выпуска.

Ошибки поднимаются с кодом ``55000`` (object_in_use) — тот же класс,
что у защиты версий статей и книг, чтобы вызывающий код обрабатывал
отказ одинаково.
"""

from alembic.operations import ops


FUNCTION_NAME = "worldloom_guard_system_rules_version"
TRUNCATE_FUNCTION_NAME = "worldloom_guard_system_rules_version_truncate"

REMOVAL_SETTING = "worldloom.removing_system_id"

TAG = "$worldloom$"

# Опубликованные версии новых разделённых таблиц наследуют ту же защиту:
# функция-гард опирается только на колонку system_id и параметр удаления
# системы, которые есть в каждой таблице версий.
SPLIT_TABLES = (
    "game_system_mechanic_versions",
    "game_system_text_versions",
    "game_system_versions",
)


# UPDATE запрещён безусловно. DELETE разрешён только когда локальный
# параметр транзакции равен system_id удаляемой строки.
GUARD_FUNCTION_SQL = f"""
CREATE OR REPLACE FUNCTION {FUNCTION_NAME}()
RETURNS trigger
LANGUAGE plpgsql
AS {TAG}
BEGIN
    IF TG_OP = 'DELETE'
       AND current_setting(
           '{REMOVAL_SETTING}',
           true
       ) = OLD.system_id::text
    THEN
        RETURN OLD;
    END IF;

    RAISE EXCEPTION
        'Published game system rule versions are immutable'
        USING ERRCODE = '55000';

    RETURN NULL;
END;
{TAG};
"""

GUARD_TRUNCATE_FUNCTION_SQL = f"""
CREATE OR REPLACE FUNCTION {TRUNCATE_FUNCTION_NAME}()
RETURNS trigger
LANGUAGE plpgsql
AS {TAG}
BEGIN
    RAISE EXCEPTION
        'Published game system rule versions cannot be truncated'
        USING ERRCODE = '55000';

    RETURN NULL;
END;
{TAG};
"""

DROP_FUNCTION_SQL = f"DROP FUNCTION IF EXISTS {FUNCTION_NAME}();"

DROP_TRUNCATE_FUNCTION_SQL = (
    f"DROP FUNCTION IF EXISTS {TRUNCATE_FUNCTION_NAME}();"
)


def _split_row_trigger_sql(table_name: str) -> str:
    return f"""
CREATE TRIGGER {table_name}_immutable
BEFORE UPDATE OR DELETE ON {table_name}
FOR EACH ROW
EXECUTE FUNCTION {FUNCTION_NAME}();
"""


def _split_truncate_trigger_sql(table_name: str) -> str:
    return f"""
CREATE TRIGGER {table_name}_no_truncate
BEFORE TRUNCATE ON {table_name}
FOR EACH STATEMENT
EXECUTE FUNCTION {TRUNCATE_FUNCTION_NAME}();
"""


def split_guard_upgrade_sql() -> tuple[str, ...]:
    """Триггеры защиты для разделённых таблиц версий.

    Функция-гард уже создана начальной миграцией и опирается только на
    колонку ``system_id`` и параметр удаления системы, поэтому для новых
    таблиц навешиваются лишь триггеры. Применяется в ревизии разделения
    сразу после создания таблиц.
    """
    statements: list[str] = []

    for table_name in SPLIT_TABLES:
        statements.append(_split_row_trigger_sql(table_name))
        statements.append(_split_truncate_trigger_sql(table_name))

    return tuple(statements)


def split_guard_downgrade_sql() -> tuple[str, ...]:
    """Снять триггеры защиты с разделённых таблиц версий."""
    statements: list[str] = []

    for table_name in SPLIT_TABLES:
        statements.append(
            f"DROP TRIGGER IF EXISTS {table_name}_immutable ON {table_name};"
        )
        statements.append(
            f"DROP TRIGGER IF EXISTS {table_name}_no_truncate ON {table_name};"
        )

    return tuple(statements)


def upgrade_operations() -> list:
    """Операции Alembic, включающие защиту версий правил."""
    return [
        ops.ExecuteSQLOp(statement)
        for statement in (
            GUARD_FUNCTION_SQL,
            GUARD_TRUNCATE_FUNCTION_SQL,
            *split_guard_upgrade_sql(),
        )
    ]


def downgrade_operations() -> list:
    """Операции Alembic, снимающие защиту версий правил."""
    return [
        ops.ExecuteSQLOp(statement)
        for statement in (
            *split_guard_downgrade_sql(),
            DROP_TRUNCATE_FUNCTION_SQL,
            DROP_FUNCTION_SQL,
        )
    ]
