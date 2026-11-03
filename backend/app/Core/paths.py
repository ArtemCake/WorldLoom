# backend/app/core/paths.py

"""Пути к исходникам, конфигурации и локальным каталогам проекта."""

from pathlib import Path


# paths.py -> core -> app -> backend -> корень проекта.
PROJECT_ROOT = Path(__file__).resolve().parents[3]

DATA_DIR = PROJECT_ROOT / "data"
ENV_FILE = DATA_DIR / ".env"

FRONTEND_DIR = PROJECT_ROOT / "frontend"
TEMPLATES_DIR = FRONTEND_DIR / "templates"
FRONTEND_PUBLIC_DIR = FRONTEND_DIR / "public"
FRONTEND_DIST_DIR = FRONTEND_DIR / "dist"
VITE_MANIFEST_FILE = FRONTEND_DIST_DIR / ".vite" / "manifest.json"

CONTENT_DIR = PROJECT_ROOT / "content"
LEGAL_CONTENT_DIR = FRONTEND_DIR / "src" / "content" / "legal"

MIGRATIONS_DIR = PROJECT_ROOT / "backend" / "db_migrations"
ALEMBIC_CONFIG_FILE = PROJECT_ROOT / "alembic.ini"

LOGS_DIR = PROJECT_ROOT / "logs"
STAGING_DIR = PROJECT_ROOT / "staging"
