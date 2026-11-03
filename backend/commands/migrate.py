# backend/app/commands/migrate.py

"""Явное применение существующих миграций без запуска веб-приложения."""

import argparse
import asyncio
import sys
from alembic import command
from alembic.config import Config
from backend.app.core.paths import ALEMBIC_CONFIG_FILE, MIGRATIONS_DIR
from backend.app.core.settings import WebAppSettings, get_settings


def build_alembic_config(settings: WebAppSettings) -> Config:
	"""Загрузить конфигурацию и передать настройки без записи URL в ini."""
	if not ALEMBIC_CONFIG_FILE.is_file():
		raise FileNotFoundError("Не найден alembic.ini в корне проекта.")

	if not (MIGRATIONS_DIR / "env.py").is_file():
		raise FileNotFoundError("Не найден backend/db_migrations/env.py.")

	versions_dir = MIGRATIONS_DIR / "versions"

	if not versions_dir.is_dir():
		raise FileNotFoundError("Не найден каталог backend/db_migrations/versions.")

	if not any(path.name != "__init__.py" for path in versions_dir.glob("*.py")):
		raise RuntimeError("Каталог versions пуст. Применение миграций остановлено.")

	config = Config(str(ALEMBIC_CONFIG_FILE))
	config.set_main_option("script_location", MIGRATIONS_DIR.as_posix().replace("%", "%%"))
	config.attributes["app_settings"] = settings
	return config

def run_migrations(settings: WebAppSettings | None = None, *, revision: str = "head", sql: bool = False) -> None:
	"""Применить миграции либо вывести SQL без его выполнения."""
	current_settings = settings if settings is not None else get_settings()
	config = build_alembic_config(current_settings)
	command.upgrade(config, revision, sql=sql)

async def apply_migrations(settings: WebAppSettings | None = None) -> None:
	"""Адаптер для вызова из асинхронного кода вне цикла Alembic."""
	await asyncio.to_thread(run_migrations, settings)

def main() -> int:
	parser = argparse.ArgumentParser(description="Применение миграций WorldLoom.")
	parser.add_argument("--revision", default="head", help="Целевая ревизия Alembic; по умолчанию head.")
	parser.add_argument("--sql", action="store_true", help="Вывести SQL без выполнения в базе данных.")
	args = parser.parse_args()

	try:
		run_migrations(revision=args.revision, sql=args.sql)
	except Exception as error:
		print(
			f"Миграции не выполнены. Тип ошибки: {type(error).__name__}. Проверьте настройки, доступ к БД и файлы миграций.",
			file=sys.stderr,
		)
		return 1

	if not args.sql:
		print("Применение миграций завершено.")

	return 0

if __name__ == "__main__":
	raise SystemExit(main())