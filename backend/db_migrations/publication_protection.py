# backend/db_migrations/publication_protection.py

"""SQL защиты опубликованных снимков статей и книг.

Опубликованные версии (``*_versions``) и их зависимости обязаны быть
неизменяемыми: их читают книги и внешние ссылки, поэтому UPDATE, DELETE и
TRUNCATE должны отклоняться на уровне СУБД, а не только в сервисе.

Ошибки поднимаются с кодом ``55000`` (object_in_use) — тот же класс, что и у
защиты ``rule_engine_versions``, чтобы вызывающий код обрабатывал отказ
одинаково.

Зависимости книги от публикаций статей (``rule_book_version_articles``)
формирует PostgreSQL: сервис публикует версию, а триггер извлекает ссылки из
оглавления. Так нельзя опубликовать книгу, чей список зависимостей расходится
с её содержанием.
"""

from alembic.operations import ops


# Тело функций обрамляется именованным тегом: он не конфликтует с
# одинарными кавычками внутри SQL и не зависит от настроек экранирования.
TAG = "$worldloom$"


def _function_sql(name: str, body: str) -> str:
    return (
        f"CREATE OR REPLACE FUNCTION {name}()\n"
        "RETURNS trigger\n"
        "LANGUAGE plpgsql\n"
        f"AS {TAG}\n"
        f"{body.strip()}\n"
        f"{TAG};\n"
    )


# Неизменяемость строки: UPDATE и DELETE запрещены безусловно.
GUARD_IMMUTABLE_FUNCTION_SQL = _function_sql(
    "worldloom_guard_publication",
    """
BEGIN
    RAISE EXCEPTION
        'Published versions are immutable'
        USING ERRCODE = '55000';

    RETURN NULL;
END;
""",
)

# TRUNCATE — отдельный вид операции, для него нужен свой триггер уровня таблицы.
GUARD_TRUNCATE_FUNCTION_SQL = _function_sql(
    "worldloom_guard_publication_truncate",
    """
BEGIN
    RAISE EXCEPTION
        'Published versions cannot be truncated'
        USING ERRCODE = '55000';

    RETURN NULL;
END;
""",
)

# Зависимость обязана ссылаться на статью, реально перечисленную в оглавлении
# публикуемой версии книги. Иначе сервис мог бы приписать лишние источники.
GUARD_DEPENDENCY_FUNCTION_SQL = _function_sql(
    "worldloom_guard_book_version_article",
    """
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM rule_book_versions AS version
        WHERE version.id = NEW.book_version_id
          AND version.content_json -> 'toc' @>
              jsonb_build_array(
                  jsonb_build_object(
                      'kind', 'article',
                      'article_version_id', NEW.article_version_id
                  )
              )
    ) THEN
        RAISE EXCEPTION
            'Book version depends on an article that its contents do not reference'
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END;
""",
)

# После вставки публикации книги извлекаем ссылки оглавления и заполняем
# зависимости уникальным набором: одна статья не попадает в список дважды.
SYNC_DEPENDENCIES_FUNCTION_SQL = _function_sql(
    "worldloom_sync_book_version_articles",
    """
BEGIN
    INSERT INTO rule_book_version_articles (book_version_id, article_version_id)
    SELECT DISTINCT
        NEW.id,
        (entry ->> 'article_version_id')::uuid
    FROM jsonb_array_elements(NEW.content_json -> 'toc') AS entry
    WHERE entry ->> 'kind' = 'article'
      AND (entry ->> 'article_version_id') IS NOT NULL;

    RETURN NEW;
END;
""",
)

# Назначенную книге систему нельзя ни заменить, ни снять: опубликованные
# версии уже привязаны к ней, а каталог фильтрует книги по системе.
GUARD_BOOK_SYSTEM_FUNCTION_SQL = _function_sql(
    "worldloom_guard_book_system",
    """
BEGIN
    IF OLD.system_id IS NOT NULL
       AND NEW.system_id IS DISTINCT FROM OLD.system_id
    THEN
        RAISE EXCEPTION
            'Assigned book system cannot be replaced or removed'
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END;
""",
)


def _immutable_trigger_sql(table: str, name: str) -> str:
    return f"""
CREATE TRIGGER {name}
BEFORE UPDATE OR DELETE ON {table}
FOR EACH ROW
EXECUTE FUNCTION worldloom_guard_publication();
"""


def _truncate_trigger_sql(table: str, name: str) -> str:
    return f"""
CREATE TRIGGER {name}
BEFORE TRUNCATE ON {table}
FOR EACH STATEMENT
EXECUTE FUNCTION worldloom_guard_publication_truncate();
"""


# Порядок важен: функции создаются раньше триггеров, которые на них ссылаются.
PROTECTED_TABLES = (
    ("rule_article_versions", "rule_article_versions_immutable", "rule_article_versions_no_truncate"),
    ("rule_book_versions", "rule_book_versions_immutable", "rule_book_versions_no_truncate"),
    ("rule_book_version_articles", "rule_book_version_articles_immutable", "rule_book_version_articles_no_truncate"),
)

CREATE_FUNCTIONS_SQL = (
    GUARD_IMMUTABLE_FUNCTION_SQL,
    GUARD_TRUNCATE_FUNCTION_SQL,
    GUARD_DEPENDENCY_FUNCTION_SQL,
    SYNC_DEPENDENCIES_FUNCTION_SQL,
    GUARD_BOOK_SYSTEM_FUNCTION_SQL,
)

CREATE_TRIGGERS_SQL = (
    *(
        statement
        for table, immutable_name, truncate_name in PROTECTED_TABLES
        for statement in (_immutable_trigger_sql(table, immutable_name),
                          _truncate_trigger_sql(table, truncate_name))
    ),
    """
CREATE TRIGGER rule_book_version_articles_source
BEFORE INSERT ON rule_book_version_articles
FOR EACH ROW
EXECUTE FUNCTION worldloom_guard_book_version_article();
""",
    """
CREATE TRIGGER rule_book_version_sync_articles
AFTER INSERT ON rule_book_versions
FOR EACH ROW
EXECUTE FUNCTION worldloom_sync_book_version_articles();
""",
    """
CREATE TRIGGER rule_books_system_immutable
BEFORE UPDATE OF system_id ON rule_books
FOR EACH ROW
EXECUTE FUNCTION worldloom_guard_book_system();
""",
)

DROP_TRIGGERS_SQL = (
    "DROP TRIGGER IF EXISTS rule_books_system_immutable ON rule_books;",
    "DROP TRIGGER IF EXISTS rule_book_version_sync_articles ON rule_book_versions;",
    "DROP TRIGGER IF EXISTS rule_book_version_articles_source ON rule_book_version_articles;",
    *(
        statement
        for table, immutable_name, truncate_name in PROTECTED_TABLES
        for statement in (f"DROP TRIGGER IF EXISTS {immutable_name} ON {table};",
                          f"DROP TRIGGER IF EXISTS {truncate_name} ON {table};")
    ),
)

DROP_FUNCTIONS_SQL = (
    "DROP FUNCTION IF EXISTS worldloom_guard_book_system();",
    "DROP FUNCTION IF EXISTS worldloom_sync_book_version_articles();",
    "DROP FUNCTION IF EXISTS worldloom_guard_book_version_article();",
    "DROP FUNCTION IF EXISTS worldloom_guard_publication_truncate();",
    "DROP FUNCTION IF EXISTS worldloom_guard_publication();",
)


def upgrade_operations() -> list:
    """Операции Alembic, включающие защиту публикаций."""
    return [ops.ExecuteSQLOp(statement) for statement in UPGRADE_SQL]


def downgrade_operations() -> list:
    """Операции Alembic, снимающие защиту публикаций."""
    return [ops.ExecuteSQLOp(statement) for statement in DOWNGRADE_SQL]


UPGRADE_SQL = CREATE_FUNCTIONS_SQL + CREATE_TRIGGERS_SQL
DOWNGRADE_SQL = DROP_TRIGGERS_SQL + DROP_FUNCTIONS_SQL
