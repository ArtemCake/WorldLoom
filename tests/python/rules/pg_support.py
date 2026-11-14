# tests/python/rules/pg_support.py

"""Подготовка временной схемы PostgreSQL для интеграционных проверок.

Имена файлов миграций не используются: цепочка ревизий строится по
``down_revision`` через :class:`alembic.script.ScriptDirectory`, а модуль
загружается по пути. Так тесты не ломаются от переименования миграции.
"""

from __future__ import annotations
import asyncio
import importlib.util
import unittest
from pathlib import Path
from uuid import uuid4
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool


MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "backend" / "db_migrations"

# Результат первой проверки подключения на процесс: повторять её для каждого
# теста незачем, но и молча падать сотней ошибок при недоступной БД нельзя.
_CONNECTION_STATE: dict[str, str | bool] = {}

# Обязательные поля users без серверных значений по умолчанию.
USER_INSERT_SQL = text(
    "INSERT INTO users (id, email_encrypted, email_hash, nickname, "
    "is_email_verified, is_active, is_2fa_enabled) "
    "VALUES (:id, :email, :email_hash, :nickname, false, true, false)"
)


def _load_migration(path: Path):
    name = f"worldloom_test_migration_{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)

    if spec is None or spec.loader is None:
        raise RuntimeError(f"Не удалось загрузить миграцию {path.name}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _describe(url: URL) -> str:
    """Описание подключения без пароля: только то, что помогает диагностике."""
    host = url.host or "?"
    port = url.port or 5432
    user = url.username or "?"
    database = url.database or "?"

    return f"пользователь {user} на {host}:{port}, база {database}"


def _connection_error(url: URL, exc: Exception) -> str:
    name = type(exc).__name__

    return (
        f"PostgreSQL недоступна ({_describe(url)}): {name}. "
        "Проверьте WORLDLOOM_RULES_TEST_URL: логин и пароль должны быть "
        "настоящими, а не плейсхолдерами вроде user:password."
    )


async def require_connection(url: URL) -> None:
    """Убедиться, что БД доступна, иначе пропустить тест с внятной причиной.

    Проверка выполняется один раз на процесс: при недоступной БД почти сотня
    тестов иначе падает одинаковым трейсбеком, в котором не видно причины.
    """
    key = url.render_as_string(hide_password=True)

    if key in _CONNECTION_STATE:
        state = _CONNECTION_STATE[key]

        if state is not True:
            raise unittest.SkipTest(str(state))

        return

    engine = create_async_engine(url, poolclass=NullPool, hide_parameters=True)

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - причина важнее типа исключения
        message = _connection_error(url, exc)
        _CONNECTION_STATE[key] = message
        raise unittest.SkipTest(message) from None
    else:
        _CONNECTION_STATE[key] = True
    finally:
        await engine.dispose()


def apply_migrations(connection) -> None:
    """Применить все ревизии по цепочке от базовой к головной."""
    script = ScriptDirectory(dir=str(MIGRATIONS_DIR))
    context = MigrationContext.configure(connection)

    with Operations.context(context):
        for revision in reversed(list(script.walk_revisions())):
            _load_migration(Path(revision.path)).upgrade()


def user_values(user_id=None) -> dict:
    """Обязательные поля users для тестовой вставки."""
    identifier = user_id or uuid4()
    suffix = uuid4().hex

    return {
        "id": identifier,
        "email": f"encrypted-{suffix}",
        "email_hash": suffix,
        "nickname": f"user-{suffix[:20]}",
    }


def system_values(system_id=None, *, active: bool = True) -> dict:
    """Обязательные поля game_systems для тестовой вставки."""
    identifier = system_id or uuid4()
    suffix = uuid4().hex

    return {
        "id": identifier,
        "name": f"Система {suffix[:12]}",
        "slug": f"system-{suffix}",
        "is_active": active,
    }


class PostgresTestCase(unittest.IsolatedAsyncioTestCase):
    """Базовый класс без asyncio-debug: он замедляет каждый тест в разы."""

    def _setupAsyncioRunner(self):
        self._asyncioRunner = asyncio.Runner(debug=False)
