# backend/db_migrations/env.py

"""Окружение Alembic с новыми настройками и единым реестром моделей."""

import asyncio
from logging.config import fileConfig
from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine
from backend.app.core.settings import WebAppSettings, get_settings
from backend.app.infrastructure.database.model_registry import load_models
from backend.db_migrations.rule_engine_protection import add_rule_engine_protection


config = context.config

if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = load_models()

def _get_settings() -> WebAppSettings:
    settings = config.attributes.get("app_settings")

    if settings is None:
        return get_settings()

    if not isinstance(settings, WebAppSettings):
        raise TypeError("В Alembic передан неподдерживаемый объект настроек.")

    return settings

def run_migrations_offline() -> None:
    """Сформировать SQL без подключения к базе данных."""
    settings = _get_settings()

    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()

def _run_migrations(connection: Connection) -> None:
    """Выполнить миграции через синхронный адаптер соединения."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        process_revision_directives=add_rule_engine_protection,
    )

    with context.begin_transaction():
        context.run_migrations()

async def _run_async_migrations() -> None:
    """Открыть отдельный движок и освободить его после операции."""
    settings = _get_settings()
    engine = create_async_engine(
        settings.DATABASE_URL,
        poolclass=pool.NullPool,
        echo=False,
        hide_parameters=True,
    )

    try:
        async with engine.connect() as connection:
            await connection.run_sync(_run_migrations)
    finally:
        await engine.dispose()

def run_migrations_online() -> None:
    """Использовать переданное соединение либо открыть собственное."""
    connection = config.attributes.get("connection")

    if connection is not None:
        if not isinstance(connection, Connection):
            raise TypeError("Alembic ожидает синхронный адаптер SQLAlchemy Connection.")

        _run_migrations(connection)
        return

    asyncio.run(_run_async_migrations())

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()