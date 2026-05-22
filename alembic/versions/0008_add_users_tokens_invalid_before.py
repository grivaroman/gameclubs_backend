"""add users tokens_invalid_before

Revision ID: 0008_add_users_tokens_invalid_before
Revises: 0007_add_package_bonus_minutes
Create Date: 2026-05-22 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008_add_users_tokens_invalid_before"
down_revision: Union[str, Sequence[str], None] = "0007_add_package_bonus_minutes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("tokens_invalid_before", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "tokens_invalid_before")
