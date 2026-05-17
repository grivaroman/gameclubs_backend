"""add pc websocket tokens

Revision ID: 0004_add_pc_websocket_tokens
Revises: 0003_add_finance_tracking
Create Date: 2026-05-17 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_add_pc_websocket_tokens"
down_revision: Union[str, Sequence[str], None] = "0003_add_finance_tracking"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("computers", sa.Column("ws_token_hash", sa.String(), nullable=True))
    op.add_column("computers", sa.Column("ws_token_created_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("computers", "ws_token_created_at")
    op.drop_column("computers", "ws_token_hash")
