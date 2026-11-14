"""Защита опубликованных снимков статей и книг

Revision ID: a1f2c3d4e5b6
Revises: 1372661e8ac9
Create Date: 2026-11-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

from backend.db_migrations.publication_protection import (
    DOWNGRADE_SQL,
    UPGRADE_SQL,
)


# revision identifiers, used by Alembic.
revision: str = 'a1f2c3d4e5b6'
down_revision: Union[str, Sequence[str], None] = '1372661e8ac9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for statement in UPGRADE_SQL:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE_SQL:
        op.execute(statement)
