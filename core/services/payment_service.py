"""Бизнес-логика пополнения баланса (тестовая интеграция Kaspi)."""
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import models
from config import settings
from core.finance import credit_user_balance
from core.services.exceptions import AuthRequiredError, FeatureDisabledError, ValidationError


@dataclass
class TopUpResult:
    amount: int
    balance: int
    reference: str
    message: str


class PaymentService:
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

    async def kaspi_test_top_up(self, *, user_id: int, amount: int) -> TopUpResult:
        if not settings.enable_kaspi_test_payment:
            raise FeatureDisabledError("Эндпоинт недоступен")
        if amount < settings.kaspi_test_min_amount or amount > settings.kaspi_test_max_amount:
            raise ValidationError(
                f"Сумма тестовой оплаты должна быть от {settings.kaspi_test_min_amount} "
                f"до {settings.kaspi_test_max_amount}₸"
            )

        user = await self._lock_active_user(user_id)

        reference = f"KASPI-TEST-{uuid4().hex[:12].upper()}"
        payment = models.PaymentTransaction(
            user_id=user.id,
            provider="kaspi_test",
            amount=amount,
            status="paid",
            external_reference=reference,
            paid_at=datetime.utcnow(),
        )
        self.db.add(payment)
        await self.db.flush()
        await credit_user_balance(
            self.db,
            user=user,
            amount=amount,
            kind="kaspi_test_top_up",
            reason="Тестовая оплата Kaspi",
            metadata={"payment_id": payment.id, "external_reference": reference, "provider": "kaspi_test"},
        )
        await self.db.commit()
        return TopUpResult(
            amount=amount,
            balance=user.balance,
            reference=reference,
            message=f"Баланс пополнен на {amount}₸",
        )
