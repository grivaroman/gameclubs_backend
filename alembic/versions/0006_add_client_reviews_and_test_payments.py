"""add client reviews and test payments

Revision ID: 0006_add_client_reviews_and_test_payments
Revises: 0005_add_integrity_constraints_and_balance_ledger
Create Date: 2026-05-18 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006_add_client_reviews_and_test_payments"
down_revision: Union[str, Sequence[str], None] = "0005_add_integrity_constraints_and_balance_ledger"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "club_reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("club_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("rating >= 1 AND rating <= 5", name="ck_club_reviews_rating_range"),
        sa.ForeignKeyConstraint(["club_id"], ["clubs.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("club_id", "user_id", name="uq_club_reviews_club_user"),
    )
    op.create_index(op.f("ix_club_reviews_id"), "club_reviews", ["id"], unique=False)
    op.create_index("ix_club_reviews_club_id", "club_reviews", ["club_id"], unique=False)
    op.create_index("ix_club_reviews_user_id", "club_reviews", ["user_id"], unique=False)
    op.create_index("ix_club_reviews_created_at", "club_reviews", ["created_at"], unique=False)

    op.create_table(
        "payment_transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("external_reference", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("amount > 0", name="ck_payment_transactions_amount_positive"),
        sa.CheckConstraint("status IN ('pending', 'paid', 'failed', 'cancelled')", name="ck_payment_transactions_status_valid"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_reference"),
    )
    op.create_index(op.f("ix_payment_transactions_id"), "payment_transactions", ["id"], unique=False)
    op.create_index("ix_payment_transactions_user_id", "payment_transactions", ["user_id"], unique=False)
    op.create_index("ix_payment_transactions_provider", "payment_transactions", ["provider"], unique=False)
    op.create_index("ix_payment_transactions_status", "payment_transactions", ["status"], unique=False)
    op.create_index("ix_payment_transactions_created_at", "payment_transactions", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_payment_transactions_created_at", table_name="payment_transactions")
    op.drop_index("ix_payment_transactions_status", table_name="payment_transactions")
    op.drop_index("ix_payment_transactions_provider", table_name="payment_transactions")
    op.drop_index("ix_payment_transactions_user_id", table_name="payment_transactions")
    op.drop_index(op.f("ix_payment_transactions_id"), table_name="payment_transactions")
    op.drop_table("payment_transactions")

    op.drop_index("ix_club_reviews_created_at", table_name="club_reviews")
    op.drop_index("ix_club_reviews_user_id", table_name="club_reviews")
    op.drop_index("ix_club_reviews_club_id", table_name="club_reviews")
    op.drop_index(op.f("ix_club_reviews_id"), table_name="club_reviews")
    op.drop_table("club_reviews")
