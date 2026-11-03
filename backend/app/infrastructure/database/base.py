# backend/app/infrastructure/database/base.py

"""Общая декларативная основа моделей SQLAlchemy."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
	"""Единая основа всех ORM-моделей приложения."""


metadata = Base.metadata