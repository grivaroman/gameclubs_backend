import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

import models


class InsufficientBalanceError(ValueError):
    pass


def encode_finance_metadata(metadata: dict[str, Any] | None) -> str | None:
    if not metadata:
        return None
    return json.dumps(metadata, ensure_ascii=False, sort_keys=True, default=str)


async def record_balance_transaction(
    db: AsyncSession,
    *,
    user: models.User,
    amount: int,
    kind: str,
    actor: models.User | None = None,
    club_id: int | None = None,
    booking_id: int | None = None,
    order_id: int | None = None,
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> models.BalanceTransaction:
    if amount == 0:
        raise ValueError("Balance transaction amount must be non-zero")

    transaction = models.BalanceTransaction(
        user_id=user.id,
        actor_user_id=actor.id if actor else None,
        club_id=club_id,
        booking_id=booking_id,
        order_id=order_id,
        amount=amount,
        balance_after=user.balance,
        kind=kind,
        reason=reason,
        metadata_json=encode_finance_metadata(metadata),
    )
    db.add(transaction)
    return transaction


async def debit_user_balance(
    db: AsyncSession,
    *,
    user: models.User,
    amount: int,
    kind: str,
    actor: models.User | None = None,
    club_id: int | None = None,
    booking_id: int | None = None,
    order_id: int | None = None,
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> models.BalanceTransaction:
    if amount <= 0:
        raise ValueError("Debit amount must be positive")
    if user.balance < amount:
        raise InsufficientBalanceError("Insufficient balance")

    user.balance -= amount
    return await record_balance_transaction(
        db,
        user=user,
        actor=actor,
        amount=-amount,
        kind=kind,
        club_id=club_id,
        booking_id=booking_id,
        order_id=order_id,
        reason=reason,
        metadata=metadata,
    )


async def credit_user_balance(
    db: AsyncSession,
    *,
    user: models.User,
    amount: int,
    kind: str,
    actor: models.User | None = None,
    club_id: int | None = None,
    booking_id: int | None = None,
    order_id: int | None = None,
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> models.BalanceTransaction:
    if amount <= 0:
        raise ValueError("Credit amount must be positive")

    user.balance += amount
    return await record_balance_transaction(
        db,
        user=user,
        actor=actor,
        amount=amount,
        kind=kind,
        club_id=club_id,
        booking_id=booking_id,
        order_id=order_id,
        reason=reason,
        metadata=metadata,
    )
