"""Бизнес-логика покупки товаров."""
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import models
from core.finance import credit_user_balance, debit_user_balance
from core.fraud import evaluate_failed_payment, evaluate_order_success
from core.services.access import user_can_manage_club
from core.services.exceptions import (
    AuthRequiredError,
    ConflictError,
    ForbiddenError,
    InsufficientFundsError,
    NotFoundError,
    ValidationError,
)


@dataclass
class OrderResult:
    order_id: int
    amount_paid: int
    message: str


@dataclass
class OrderCancelResult:
    order_id: int
    refunded: int
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

    async def cancel_order(self, *, actor: models.User, order_id: int) -> OrderCancelResult:
        """M4: владелец клуба/суперадмин отменяет заказ и возвращает деньги покупателю.

        Идемпотентно (повторная отмена → 0 возврата). Выполненный заказ
        (status='completed') отменить с возвратом нельзя.
        """
        res = await self.db.execute(
            select(models.Order).filter(models.Order.id == order_id).with_for_update()
        )
        order = res.scalars().first()
        if not order:
            raise NotFoundError("Заказ не найден")

        res_prod = await self.db.execute(
            select(models.Product).filter(models.Product.id == order.product_id)
        )
        product = res_prod.scalars().first()
        if not product or not await user_can_manage_club(self.db, actor, product.club_id):
            raise ForbiddenError("Нет доступа к этому заказу")

        if order.status == "cancelled":
            return OrderCancelResult(order_id=order.id, refunded=0, message="Заказ уже отменён")
        if order.status == "completed":
            raise ConflictError("Заказ уже выполнен — отмена с возвратом недоступна")

        refunded = 0
        if order.amount_paid and order.amount_paid > 0 and order.user_id:
            res_user = await self.db.execute(
                select(models.User).filter(models.User.id == order.user_id).with_for_update()
            )
            buyer = res_user.scalars().first()
            if buyer:
                await credit_user_balance(
                    self.db,
                    user=buyer,
                    amount=order.amount_paid,
                    kind="order_refund",
                    actor=actor,
                    club_id=product.club_id,
                    order_id=order.id,
                    reason="Возврат за отменённый заказ",
                )
                refunded = order.amount_paid

        order.status = "cancelled"
        self.db.add(models.Notification(
            kind="order",
            club_id=product.club_id,
            title="Заказ отменён",
            message=f"Заказ #{order.id} отменён{' (деньги возвращены)' if refunded else ''}.",
        ))
        await self.db.commit()
        return OrderCancelResult(order_id=order.id, refunded=refunded, message="Заказ отменён.")
