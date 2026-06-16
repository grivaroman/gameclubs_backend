"""add club booking mode and deposit

Revision ID: 0010_add_club_booking_mode
Revises: 0009_add_booking_pending_status
Create Date: 2026-06-17 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010_add_club_booking_mode"
down_revision: Union[str, Sequence[str], None] = "0009_add_booking_pending_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clubs", sa.Column("booking_mode", sa.String(), server_default="request", nullable=True))
    op.add_column("clubs", sa.Column("booking_deposit", sa.Integer(), server_default="0", nullable=True))
    op.create_check_constraint(
        "ck_clubs_booking_mode_valid",
        "clubs",
        "booking_mode IS NULL OR booking_mode IN ('request', 'prepaid')",
    )
    op.create_check_constraint(
        "ck_clubs_booking_deposit_non_negative",
        "clubs",
        "booking_deposit IS NULL OR booking_deposit >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_clubs_booking_deposit_non_negative", "clubs", type_="check")
    op.drop_constraint("ck_clubs_booking_mode_valid", "clubs", type_="check")
    op.drop_column("clubs", "booking_deposit")
    op.drop_column("clubs", "booking_mode")
