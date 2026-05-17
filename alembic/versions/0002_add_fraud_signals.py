"""add fraud signals

Revision ID: 0002_add_fraud_signals
Revises: 0001_initial_schema
Create Date: 2026-05-16 01:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_add_fraud_signals"
down_revision: Union[str, Sequence[str], None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fraud_signals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("actor_role", sa.String(), nullable=True),
        sa.Column("subject_user_id", sa.Integer(), nullable=True),
        sa.Column("club_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["club_id"], ["clubs.id"]),
        sa.ForeignKeyConstraint(["subject_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_fraud_signals_id"), "fraud_signals", ["id"], unique=False)
    op.create_index("ix_fraud_signals_event_type", "fraud_signals", ["event_type"], unique=False)
    op.create_index("ix_fraud_signals_status", "fraud_signals", ["status"], unique=False)
    op.create_index("ix_fraud_signals_created_at", "fraud_signals", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_fraud_signals_created_at", table_name="fraud_signals")
    op.drop_index("ix_fraud_signals_status", table_name="fraud_signals")
    op.drop_index("ix_fraud_signals_event_type", table_name="fraud_signals")
    op.drop_index(op.f("ix_fraud_signals_id"), table_name="fraud_signals")
    op.drop_table("fraud_signals")
