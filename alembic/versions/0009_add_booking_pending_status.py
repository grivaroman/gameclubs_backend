"""add booking pending and rejected statuses

Revision ID: 0009_add_booking_pending_status
Revises: 0008_add_users_tokens_invalid_before
Create Date: 2026-06-16 00:00:00

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0009_add_booking_pending_status"
down_revision: Union[str, Sequence[str], None] = "0008_add_users_tokens_invalid_before"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_bookings_status_valid", "bookings", type_="check")
    op.create_check_constraint(
        "ck_bookings_status_valid",
        "bookings",
        "status IS NULL OR status IN ('pending', 'active', 'completed', 'expired', 'cancelled', 'rejected')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_bookings_status_valid", "bookings", type_="check")
    op.create_check_constraint(
        "ck_bookings_status_valid",
        "bookings",
        "status IS NULL OR status IN ('active', 'completed', 'expired', 'cancelled')",
    )
