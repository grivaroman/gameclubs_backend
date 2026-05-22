"""add package bonus minutes

Revision ID: 0007_add_package_bonus_minutes
Revises: 0006_add_client_reviews_and_test_payments
Create Date: 2026-05-18 00:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007_add_package_bonus_minutes"
down_revision: Union[str, Sequence[str], None] = "0006_add_client_reviews_and_test_payments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("packages", sa.Column("paid_minutes", sa.Integer(), nullable=True))
    op.add_column("packages", sa.Column("bonus_minutes", sa.Integer(), nullable=True))
    op.execute("UPDATE packages SET paid_minutes = duration_minutes WHERE paid_minutes IS NULL")
    op.execute("UPDATE packages SET bonus_minutes = 0 WHERE bonus_minutes IS NULL")
    op.create_check_constraint("ck_packages_paid_minutes_positive", "packages", "paid_minutes IS NULL OR paid_minutes > 0")
    op.create_check_constraint("ck_packages_bonus_minutes_non_negative", "packages", "bonus_minutes IS NULL OR bonus_minutes >= 0")


def downgrade() -> None:
    op.drop_constraint("ck_packages_bonus_minutes_non_negative", "packages", type_="check")
    op.drop_constraint("ck_packages_paid_minutes_positive", "packages", type_="check")
    op.drop_column("packages", "bonus_minutes")
    op.drop_column("packages", "paid_minutes")
