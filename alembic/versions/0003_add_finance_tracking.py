"""add finance tracking

Revision ID: 0003_add_finance_tracking
Revises: 0002_add_fraud_signals
Create Date: 2026-05-16 02:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_add_finance_tracking"
down_revision: Union[str, Sequence[str], None] = "0002_add_fraud_signals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bookings", sa.Column("amount_paid", sa.Integer(), nullable=True))
    op.add_column("orders", sa.Column("amount_paid", sa.Integer(), nullable=True))
    op.execute("UPDATE bookings SET amount_paid = 0 WHERE amount_paid IS NULL")
    op.execute("UPDATE orders SET amount_paid = 0 WHERE amount_paid IS NULL")

    op.create_table(
        "expenses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("club_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("spent_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["club_id"], ["clubs.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_expenses_id"), "expenses", ["id"], unique=False)
    op.create_index("ix_expenses_club_id", "expenses", ["club_id"], unique=False)
    op.create_index("ix_expenses_spent_at", "expenses", ["spent_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_expenses_spent_at", table_name="expenses")
    op.drop_index("ix_expenses_club_id", table_name="expenses")
    op.drop_index(op.f("ix_expenses_id"), table_name="expenses")
    op.drop_table("expenses")
    op.drop_column("orders", "amount_paid")
    op.drop_column("bookings", "amount_paid")
