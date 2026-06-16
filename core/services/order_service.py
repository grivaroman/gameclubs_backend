"""Бизнес-логика покупки товаров."""
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import models
from core.finance import debit_user_balance
from core.fraud import evaluate_failed_payment, evaluate_order_success
from core.services.exceptions import (
    AuthRequiredError,
    ConflictError,
    InsufficientFundsError,
    NotFoundError,
    ValidationError,
)


@dataclass
class OrderResult:
    order_id: int
    amount_paid: int
    message: str


class OrderService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _lock_active_user(self, user_id: int) -> models.User:
        res = await self.db.execute(
            select(models.User)
            .filter(models.User.id == user_id, models.User.is_active == 1)
            .with_for_update()
        )
        user = res.scalars().first()
        if not user:
            raise AuthRequiredError("Необходима авторизация")
        return user

    async def buy_product(self, *, user_id: int, product_id: int) -> OrderResult:
        user = await self._lock_active_user(user_id)

        res_prod = await self.db.execute(
            select(models.Product).filter(models.Product.id == product_id)
        )
        product = res_prod.scalars().first()
        if not product:
            raise NotFoundError("Товар не найден")

        res_club = await self.db.execute(
            select(models.Club.id).filter(
                models.Club.id == product.club_id,
                models.Club.status == "active",
            )
        )
        if not res_club.scalars().first():
            raise ConflictError("Клуб сейчас недоступен для заказов")
        if product.price < 0:
            raise ValidationError("Товар настроен некорректно")

        if user.balance < product.price:
            await evaluate_failed_payment(
                self.db,
                user=user,
                event_type="player_order_insufficient_funds",
                amount=product.price,
                balance=user.balance,
                club_id=product.club_id,
            )
            await self.db.commit()
            raise InsufficientFundsError("Недостаточно средств на балансе")

        order = models.Order(
            user_id=user.id,
            product_id=product_id,
            amount_paid=product.price,
            status="new",
        )
        self.db.add(order)
        await self.db.flush()
        await debit_user_balance(
            self.db,
            user=user,
            amount=product.price,
            kind="order_debit",
            club_id=product.club_id,
            order_id=order.id,
            reason="Покупка товара",
            metadata={"product_id": product.id},
        )
        self.db.add(models.Notification(
            kind="order",
            club_id=product.club_id,
            title="Новый заказ",
            message=f"Заказали товар: {product.name}.",
        ))
        await evaluate_order_success(self.db, user=user, product=product)
        await self.db.commit()
        return OrderResult(
            order_id=order.id,
            amount_paid=product.price,
            message=f"Заказ принят! Списано {product.price}₸",
        )
