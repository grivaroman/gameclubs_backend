"""add integrity constraints and balance ledger

Revision ID: 0005_add_integrity_constraints_and_balance_ledger
Revises: 0004_add_pc_websocket_tokens
Create Date: 2026-05-17 00:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005_add_integrity_constraints_and_balance_ledger"
down_revision: Union[str, Sequence[str], None] = "0004_add_pc_websocket_tokens"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "balance_transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("club_id", sa.Integer(), nullable=True),
        sa.Column("booking_id", sa.Integer(), nullable=True),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("amount <> 0", name="ck_balance_transactions_amount_non_zero"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"]),
        sa.ForeignKeyConstraint(["club_id"], ["clubs.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_balance_transactions_id"), "balance_transactions", ["id"], unique=False)
    op.create_index("ix_balance_transactions_user_id", "balance_transactions", ["user_id"], unique=False)
    op.create_index("ix_balance_transactions_actor_user_id", "balance_transactions", ["actor_user_id"], unique=False)
    op.create_index("ix_balance_transactions_club_id", "balance_transactions", ["club_id"], unique=False)
    op.create_index("ix_balance_transactions_created_at", "balance_transactions", ["created_at"], unique=False)
    op.create_index("ix_balance_transactions_kind", "balance_transactions", ["kind"], unique=False)

    op.create_check_constraint("ck_users_balance_non_negative", "users", "balance IS NULL OR balance >= 0")
    op.create_check_constraint("ck_users_is_active_boolean", "users", "is_active IS NULL OR is_active IN (0, 1)")
    op.create_check_constraint(
        "ck_users_role_valid",
        "users",
        "role IS NULL OR role IN ('user', 'pending_owner', 'admin', 'owner', 'superadmin')",
    )

    op.create_check_constraint(
        "ck_clubs_status_valid",
        "clubs",
        "status IS NULL OR status IN ('pending', 'active', 'blocked', 'rejected')",
    )
    op.create_index("ix_clubs_owner_id", "clubs", ["owner_id"], unique=False)
    op.create_index("ix_clubs_status", "clubs", ["status"], unique=False)

    op.create_check_constraint("ck_computers_number_positive", "computers", "number IS NULL OR number > 0")
    op.create_check_constraint(
        "ck_computers_status_valid",
        "computers",
        "status IS NULL OR status IN ('free', 'busy', 'reserved')",
    )
    op.create_unique_constraint("uq_computers_club_number", "computers", ["club_id", "number"])
    op.create_index("ix_computers_club_id", "computers", ["club_id"], unique=False)
    op.create_index("ix_computers_status", "computers", ["status"], unique=False)

    op.create_check_constraint("ck_products_price_non_negative", "products", "price IS NULL OR price >= 0")
    op.create_index("ix_products_club_id", "products", ["club_id"], unique=False)

    op.create_check_constraint("ck_packages_price_non_negative", "packages", "price IS NULL OR price >= 0")
    op.create_check_constraint("ck_packages_duration_positive", "packages", "duration_minutes IS NULL OR duration_minutes > 0")
    op.create_index("ix_packages_club_id", "packages", ["club_id"], unique=False)

    op.create_check_constraint("ck_orders_amount_paid_non_negative", "orders", "amount_paid IS NULL OR amount_paid >= 0")
    op.create_check_constraint(
        "ck_orders_status_valid",
        "orders",
        "status IS NULL OR status IN ('pending', 'new', 'completed', 'cancelled')",
    )
    op.create_index("ix_orders_user_id", "orders", ["user_id"], unique=False)
    op.create_index("ix_orders_product_id", "orders", ["product_id"], unique=False)
    op.create_index("ix_orders_status", "orders", ["status"], unique=False)
    op.create_index("ix_orders_created_at", "orders", ["created_at"], unique=False)

    op.create_check_constraint("ck_bookings_amount_paid_non_negative", "bookings", "amount_paid IS NULL OR amount_paid >= 0")
    op.create_check_constraint(
        "ck_bookings_status_valid",
        "bookings",
        "status IS NULL OR status IN ('active', 'completed', 'expired', 'cancelled')",
    )
    op.create_index("ix_bookings_user_id", "bookings", ["user_id"], unique=False)
    op.create_index("ix_bookings_computer_id", "bookings", ["computer_id"], unique=False)
    op.create_index("ix_bookings_status", "bookings", ["status"], unique=False)
    op.create_index("ix_bookings_starts_at", "bookings", ["starts_at"], unique=False)

    op.create_check_constraint("ck_expenses_amount_positive", "expenses", "amount > 0")

    op.create_check_constraint("ck_notifications_is_read_boolean", "notifications", "is_read IS NULL OR is_read IN (0, 1)")
    op.create_index("ix_notifications_club_id", "notifications", ["club_id"], unique=False)
    op.create_index("ix_notifications_is_read", "notifications", ["is_read"], unique=False)
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"], unique=False)

    op.create_check_constraint("ck_fraud_signals_score_range", "fraud_signals", "score IS NULL OR (score >= 0 AND score <= 100)")
    op.create_check_constraint(
        "ck_fraud_signals_severity_valid",
        "fraud_signals",
        "severity IS NULL OR severity IN ('low', 'medium', 'high')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_fraud_signals_severity_valid", "fraud_signals", type_="check")
    op.drop_constraint("ck_fraud_signals_score_range", "fraud_signals", type_="check")

    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_index("ix_notifications_is_read", table_name="notifications")
    op.drop_index("ix_notifications_club_id", table_name="notifications")
    op.drop_constraint("ck_notifications_is_read_boolean", "notifications", type_="check")

    op.drop_constraint("ck_expenses_amount_positive", "expenses", type_="check")

    op.drop_index("ix_bookings_starts_at", table_name="bookings")
    op.drop_index("ix_bookings_status", table_name="bookings")
    op.drop_index("ix_bookings_computer_id", table_name="bookings")
    op.drop_index("ix_bookings_user_id", table_name="bookings")
    op.drop_constraint("ck_bookings_status_valid", "bookings", type_="check")
    op.drop_constraint("ck_bookings_amount_paid_non_negative", "bookings", type_="check")

    op.drop_index("ix_orders_created_at", table_name="orders")
    op.drop_index("ix_orders_status", table_name="orders")
    op.drop_index("ix_orders_product_id", table_name="orders")
    op.drop_index("ix_orders_user_id", table_name="orders")
    op.drop_constraint("ck_orders_status_valid", "orders", type_="check")
    op.drop_constraint("ck_orders_amount_paid_non_negative", "orders", type_="check")

    op.drop_index("ix_packages_club_id", table_name="packages")
    op.drop_constraint("ck_packages_duration_positive", "packages", type_="check")
    op.drop_constraint("ck_packages_price_non_negative", "packages", type_="check")

    op.drop_index("ix_products_club_id", table_name="products")
    op.drop_constraint("ck_products_price_non_negative", "products", type_="check")

    op.drop_index("ix_computers_status", table_name="computers")
    op.drop_index("ix_computers_club_id", table_name="computers")
    op.drop_constraint("uq_computers_club_number", "computers", type_="unique")
    op.drop_constraint("ck_computers_status_valid", "computers", type_="check")
    op.drop_constraint("ck_computers_number_positive", "computers", type_="check")

    op.drop_index("ix_clubs_status", table_name="clubs")
    op.drop_index("ix_clubs_owner_id", table_name="clubs")
    op.drop_constraint("ck_clubs_status_valid", "clubs", type_="check")

    op.drop_constraint("ck_users_role_valid", "users", type_="check")
    op.drop_constraint("ck_users_is_active_boolean", "users", type_="check")
    op.drop_constraint("ck_users_balance_non_negative", "users", type_="check")

    op.drop_index("ix_balance_transactions_kind", table_name="balance_transactions")
    op.drop_index("ix_balance_transactions_created_at", table_name="balance_transactions")
    op.drop_index("ix_balance_transactions_club_id", table_name="balance_transactions")
    op.drop_index("ix_balance_transactions_actor_user_id", table_name="balance_transactions")
    op.drop_index("ix_balance_transactions_user_id", table_name="balance_transactions")
    op.drop_index(op.f("ix_balance_transactions_id"), table_name="balance_transactions")
    op.drop_table("balance_transactions")
