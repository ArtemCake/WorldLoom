"""Защита опубликованных версий статей и книг

Revision ID: 47b059d75bdc
Revises: ce197d4917e3
Create Date: 2026-11-14 16:42:41.247848

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from backend.db_migrations.publication_protection import (
    DOWNGRADE_SQL,
    UPGRADE_SQL,
)


# revision identifiers, used by Alembic.
revision: str = '47b059d75bdc'
down_revision: Union[str, Sequence[str], None] = 'ce197d4917e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Включить функции и триггеры защиты публикаций."""
    for statement in UPGRADE_SQL:
        op.execute(statement)


def downgrade() -> None:
    """Снять триггеры и функции защиты публикаций."""
    for statement in DOWNGRADE_SQL:
        op.execute(statement)
