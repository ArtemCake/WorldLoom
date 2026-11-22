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


TABLE_NAME = "game_system_rules_versions"
ROW_TRIGGER_NAME = "game_system_rules_versions_immutable"
TRUNCATE_TRIGGER_NAME = "game_system_rules_versions_no_truncate"
FUNCTION_NAME = "worldloom_guard_system_rules_version"
TRUNCATE_FUNCTION_NAME = "worldloom_guard_system_rules_version_truncate"

REMOVAL_SETTING = "worldloom.removing_system_id"

TAG = "$worldloom$"


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

CREATE_ROW_TRIGGER_SQL = f"""
CREATE TRIGGER {ROW_TRIGGER_NAME}
BEFORE UPDATE OR DELETE ON {TABLE_NAME}
FOR EACH ROW
EXECUTE FUNCTION {FUNCTION_NAME}();
"""

CREATE_TRUNCATE_TRIGGER_SQL = f"""
CREATE TRIGGER {TRUNCATE_TRIGGER_NAME}
BEFORE TRUNCATE ON {TABLE_NAME}
FOR EACH STATEMENT
EXECUTE FUNCTION {TRUNCATE_FUNCTION_NAME}();
"""

DROP_ROW_TRIGGER_SQL = (
    f"DROP TRIGGER IF EXISTS {ROW_TRIGGER_NAME} ON {TABLE_NAME};"
)

DROP_TRUNCATE_TRIGGER_SQL = (
    f"DROP TRIGGER IF EXISTS {TRUNCATE_TRIGGER_NAME} ON {TABLE_NAME};"
)

DROP_FUNCTION_SQL = f"DROP FUNCTION IF EXISTS {FUNCTION_NAME}();"

DROP_TRUNCATE_FUNCTION_SQL = (
    f"DROP FUNCTION IF EXISTS {TRUNCATE_FUNCTION_NAME}();"
)

# Порядок важен: функции создаются раньше ссылающихся на них триггеров.
UPGRADE_SQL = (
    GUARD_FUNCTION_SQL,
    GUARD_TRUNCATE_FUNCTION_SQL,
    CREATE_ROW_TRIGGER_SQL,
    CREATE_TRUNCATE_TRIGGER_SQL,
)

# Откат снимает триггеры раньше функций.
DOWNGRADE_SQL = (
    DROP_ROW_TRIGGER_SQL,
    DROP_TRUNCATE_TRIGGER_SQL,
    DROP_FUNCTION_SQL,
    DROP_TRUNCATE_FUNCTION_SQL,
)


def upgrade_operations() -> list:
    """Операции Alembic, включающие защиту версий правил."""
    return [ops.ExecuteSQLOp(statement) for statement in UPGRADE_SQL]


def downgrade_operations() -> list:
    """Операции Alembic, снимающие защиту версий правил."""
    return [ops.ExecuteSQLOp(statement) for statement in DOWNGRADE_SQL]
