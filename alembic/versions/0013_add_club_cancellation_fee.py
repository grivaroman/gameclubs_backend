"""add clubs.cancellation_fee_percent (non-refundable deposit on player cancel)

Revision ID: 0013_add_club_cancellation_fee
Revises: 0012_add_idempotency_keys
Create Date: 2026-06-26 00:00:00

Невозвратный задаток при отмене брони игроком: процент от предоплаты остаётся
у мерчанта. При отмене возврат = предоплата − задаток. При отклонении владельцем
или протухании заявки возвращается всё (не вина клиента).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0013_add_club_cancellation_fee"
down_revision: Union[str, Sequence[str], None] = "0012_add_idempotency_keys"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "clubs",
        sa.Column("cancellation_fee_percent", sa.Integer(), nullable=True, server_default="0"),
    )
    op.create_check_constraint(
        "ck_clubs_cancellation_fee_percent_range",
        "clubs",
        "cancellation_fee_percent IS NULL OR (cancellation_fee_percent >= 0 AND cancellation_fee_percent <= 100)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_clubs_cancellation_fee_percent_range", "clubs", type_="check")
    op.drop_column("clubs", "cancellation_fee_percent")
