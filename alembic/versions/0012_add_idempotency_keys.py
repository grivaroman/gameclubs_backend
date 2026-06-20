"""add idempotency_keys for money actions

Revision ID: 0012_add_idempotency_keys
Revises: 0011_add_refresh_tokens
Create Date: 2026-06-20 01:00:00

Идемпотентность денежных POST-действий: клиент шлёт Idempotency-Key,
повторный запрос с тем же ключом возвращает сохранённый ответ.
Уникальность (user_id, idem_key) защищает от двойного списания при гонке.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0012_add_idempotency_keys"
down_revision: Union[str, Sequence[str], None] = "0011_add_refresh_tokens"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("idem_key", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="in_progress"),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "idem_key", name="uq_idempotency_user_key"),
    )
    op.create_index("ix_idempotency_keys_created_at", "idempotency_keys", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_idempotency_keys_created_at", table_name="idempotency_keys")
    op.drop_table("idempotency_keys")
