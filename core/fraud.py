import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import models

SEVERITY_LOW = "low"
SEVERITY_MEDIUM = "medium"
SEVERITY_HIGH = "high"

HIGH_VALUE_BOOKING_PRICE = 20_000
HIGH_VALUE_PRODUCT_PRICE = 10_000
HIGH_VALUE_TOP_UP_AMOUNT = 50_000
CUMULATIVE_BOOKING_AMOUNT_15M = 35_000
CUMULATIVE_ORDER_AMOUNT_10M = 25_000
CUMULATIVE_TOP_UP_AMOUNT_24H = 100_000
RAPID_BOOKING_LIMIT = 3
RAPID_ORDER_LIMIT = 5
FREQUENT_TOP_UP_LIMIT = 5


def severity_for_score(score: int) -> str:
    if score >= 80:
        return SEVERITY_HIGH
    if score >= 50:
        return SEVERITY_MEDIUM
    return SEVERITY_LOW


def encode_metadata(metadata: dict[str, Any] | None) -> str | None:
    if not metadata:
        return None
    return json.dumps(metadata, ensure_ascii=False, sort_keys=True, default=str)


async def create_fraud_signal(
    db: AsyncSession,
    *,
    actor: models.User | None,
    event_type: str,
    score: int,
    reason: str,
    club_id: int | None = None,
    subject_user_id: int | None = None,
    metadata: dict[str, Any] | None = None,
):
    db.add(models.FraudSignal(
        actor_user_id=actor.id if actor else None,
        actor_role=actor.role if actor else None,
        subject_user_id=subject_user_id,
        club_id=club_id,
        event_type=event_type,
        severity=severity_for_score(score),
        score=score,
        reason=reason,
        metadata_json=encode_metadata(metadata),
        status="open",
    ))


async def recent_fraud_count(
    db: AsyncSession,
    *,
    actor_user_id: int,
    event_type: str,
    since: datetime,
) -> int:
    res = await db.execute(
        select(func.count(models.FraudSignal.id)).filter(
            models.FraudSignal.actor_user_id == actor_user_id,
            models.FraudSignal.event_type == event_type,
            models.FraudSignal.created_at >= since,
        )
    )
    return res.scalar() or 0


async def evaluate_failed_payment(
    db: AsyncSession,
    *,
    user: models.User,
    event_type: str,
    amount: int,
    balance: int,
    club_id: int | None,
):
    since = datetime.utcnow() - timedelta(minutes=15)
    previous_count = await recent_fraud_count(db, actor_user_id=user.id, event_type=event_type, since=since)
    score = 35 + min(previous_count * 15, 45)
    await create_fraud_signal(
        db,
        actor=user,
        event_type=event_type,
        score=score,
        club_id=club_id,
        reason="Попытка операции при недостаточном балансе",
        metadata={"amount": amount, "balance": balance, "recent_failed_attempts": previous_count + 1},
    )


async def evaluate_booking_success(
    db: AsyncSession,
    *,
    user: models.User,
    pc: models.Computer,
    package: models.Package,
):
    if package.price >= HIGH_VALUE_BOOKING_PRICE:
        await create_fraud_signal(
            db,
            actor=user,
            event_type="player_high_value_booking",
            score=65,
            club_id=pc.club_id,
            reason="Дорогая бронь игрока",
            metadata={"pc_id": pc.id, "package_id": package.id, "price": package.price},
        )

    since = datetime.utcnow() - timedelta(minutes=15)
    res = await db.execute(
        select(func.count(models.Booking.id)).filter(
            models.Booking.user_id == user.id,
            models.Booking.starts_at >= since,
        )
    )
    recent_bookings = (res.scalar() or 0) + 1
    if recent_bookings >= RAPID_BOOKING_LIMIT:
        await create_fraud_signal(
            db,
            actor=user,
            event_type="player_rapid_bookings",
            score=70,
            club_id=pc.club_id,
            reason="Много броней за короткий период",
            metadata={"recent_bookings_15m": recent_bookings, "pc_id": pc.id},
        )

    res_amount = await db.execute(
        select(func.coalesce(func.sum(models.Booking.amount_paid), 0)).filter(
            models.Booking.user_id == user.id,
            models.Booking.starts_at >= since,
        )
    )
    recent_amount = (res_amount.scalar() or 0) + package.price
    if recent_amount >= CUMULATIVE_BOOKING_AMOUNT_15M:
        await create_fraud_signal(
            db,
            actor=user,
            event_type="player_cumulative_booking_spend",
            score=75,
            club_id=pc.club_id,
            reason="Высокая суммарная стоимость броней за короткий период",
            metadata={
                "recent_booking_amount_15m": recent_amount,
                "current_price": package.price,
                "pc_id": pc.id,
            },
        )


async def evaluate_order_success(
    db: AsyncSession,
    *,
    user: models.User,
    product: models.Product,
):
    if product.price >= HIGH_VALUE_PRODUCT_PRICE:
        await create_fraud_signal(
            db,
            actor=user,
            event_type="player_high_value_order",
            score=60,
            club_id=product.club_id,
            reason="Дорогой заказ товара",
            metadata={"product_id": product.id, "price": product.price},
        )

    since = datetime.utcnow() - timedelta(minutes=10)
    res = await db.execute(
        select(func.count(models.Order.id)).filter(
            models.Order.user_id == user.id,
            models.Order.created_at >= since,
        )
    )
    recent_orders = (res.scalar() or 0) + 1
    if recent_orders >= RAPID_ORDER_LIMIT:
        await create_fraud_signal(
            db,
            actor=user,
            event_type="player_rapid_orders",
            score=75,
            club_id=product.club_id,
            reason="Много заказов за короткий период",
            metadata={"recent_orders_10m": recent_orders, "product_id": product.id},
        )

    res_amount = await db.execute(
        select(func.coalesce(func.sum(models.Order.amount_paid), 0)).filter(
            models.Order.user_id == user.id,
            models.Order.created_at >= since,
        )
    )
    recent_amount = (res_amount.scalar() or 0) + product.price
    if recent_amount >= CUMULATIVE_ORDER_AMOUNT_10M:
        await create_fraud_signal(
            db,
            actor=user,
            event_type="player_cumulative_order_spend",
            score=75,
            club_id=product.club_id,
            reason="Высокая суммарная стоимость заказов за короткий период",
            metadata={
                "recent_order_amount_10m": recent_amount,
                "current_price": product.price,
                "product_id": product.id,
            },
        )


async def evaluate_admin_top_up(
    db: AsyncSession,
    *,
    admin: models.User,
    target_user: models.User,
    amount: int,
):
    if amount >= HIGH_VALUE_TOP_UP_AMOUNT:
        await create_fraud_signal(
            db,
            actor=admin,
            event_type="admin_high_value_top_up",
            score=80,
            subject_user_id=target_user.id,
            reason="Крупное ручное пополнение баланса",
            metadata={"amount": amount, "target_balance_after": target_user.balance},
        )

    since = datetime.utcnow() - timedelta(hours=24)
    res = await db.execute(
        select(func.count(models.FraudSignal.id)).filter(
            models.FraudSignal.actor_user_id == admin.id,
            models.FraudSignal.event_type == "admin_top_up_observed",
            models.FraudSignal.created_at >= since,
        )
    )
    recent_topups = res.scalar() or 0
    observed_topups = recent_topups + 1
    await create_fraud_signal(
        db,
        actor=admin,
        event_type="admin_top_up_observed",
        score=25 if observed_topups < FREQUENT_TOP_UP_LIMIT else 55,
        subject_user_id=target_user.id,
        reason="Ручное пополнение баланса администратором",
        metadata={"amount": amount, "recent_topups_24h": observed_topups},
    )

    res_topups = await db.execute(
        select(models.FraudSignal.metadata_json).filter(
            models.FraudSignal.actor_user_id == admin.id,
            models.FraudSignal.event_type == "admin_top_up_observed",
            models.FraudSignal.created_at >= since,
        )
    )
    recent_amount = amount
    for metadata_json in res_topups.scalars().all():
        try:
            recent_amount += int((json.loads(metadata_json or "{}").get("amount") or 0))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue

    if recent_amount >= CUMULATIVE_TOP_UP_AMOUNT_24H:
        await create_fraud_signal(
            db,
            actor=admin,
            event_type="admin_cumulative_top_up_risk",
            score=80,
            subject_user_id=target_user.id,
            reason="Крупная суммарная сумма ручных пополнений за сутки",
            metadata={
                "current_amount": amount,
                "observed_topups_24h": observed_topups,
                "recent_top_up_amount_24h": recent_amount,
            },
        )


async def evaluate_admin_pc_override(
    db: AsyncSession,
    *,
    admin: models.User,
    pc: models.Computer,
    new_status: str,
):
    score = 45
    reason = "Ручное изменение статуса ПК администратором"
    if new_status == "free" and pc.current_user_id:
        score = 70
        reason = "Администратор освободил занятый ПК пользователя"

    await create_fraud_signal(
        db,
        actor=admin,
        event_type="admin_pc_status_override",
        score=score,
        club_id=pc.club_id,
        subject_user_id=pc.current_user_id,
        reason=reason,
        metadata={"pc_id": pc.id, "pc_number": pc.number, "new_status": new_status},
    )
