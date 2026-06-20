"""M4: OrderService.cancel_order — возврат денег покупателю при отмене заказа,
tenancy (только владелец клуба товара), идемпотентность, запрет отмены
выполненного заказа.
"""
import unittest

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.future import select
from sqlalchemy.orm import sessionmaker

import models
from core.services.order_service import OrderService
from core.services.exceptions import ConflictError, ForbiddenError


class OrderRefundTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(models.Base.metadata.create_all)
        self.Session = sessionmaker(bind=self.engine, class_=AsyncSession, expire_on_commit=False)
        self.original_session_local = models.SessionLocal
        models.SessionLocal = self.Session

        async with self.Session() as db:
            owner = models.User(email="owner@x.com", hashed_password="x", role="owner", is_active=1, balance=0)
            other = models.User(email="other@x.com", hashed_password="x", role="owner", is_active=1, balance=0)
            buyer = models.User(email="buyer@x.com", hashed_password="x", role="user", is_active=1, balance=2000)
            db.add_all([owner, other, buyer])
            await db.flush()
            self.owner_id, self.other_id, self.buyer_id = owner.id, other.id, buyer.id

            club = models.Club(name="C", address="A", owner_id=owner.id, status="active")
            db.add(club)
            await db.flush()
            self.club_id = club.id
            product = models.Product(name="Cola", price=500, club_id=club.id)
            db.add(product)
            await db.flush()
            self.product_id = product.id
            await db.commit()

    async def asyncTearDown(self):
        models.SessionLocal = self.original_session_local
        await self.engine.dispose()

    async def _user(self, db, uid):
        return (await db.execute(select(models.User).filter(models.User.id == uid))).scalars().first()

    async def _balance(self, uid):
        async with self.Session() as db:
            return (await self._user(db, uid)).balance

    async def _make_order(self):
        async with self.Session() as db:
            res = await OrderService(db).buy_product(user_id=self.buyer_id, product_id=self.product_id)
            return res.order_id

    async def test_cancel_refunds_buyer(self):
        order_id = await self._make_order()
        self.assertEqual(await self._balance(self.buyer_id), 1500)   # 2000 - 500
        async with self.Session() as db:
            owner = await self._user(db, self.owner_id)
            result = await OrderService(db).cancel_order(actor=owner, order_id=order_id)
        self.assertEqual(result.refunded, 500)
        self.assertEqual(await self._balance(self.buyer_id), 2000)   # возврат
        async with self.Session() as db:
            order = (await db.execute(select(models.Order).filter(models.Order.id == order_id))).scalars().first()
            self.assertEqual(order.status, "cancelled")

    async def test_other_owner_cannot_cancel(self):
        order_id = await self._make_order()
        async with self.Session() as db:
            other = await self._user(db, self.other_id)
            with self.assertRaises(ForbiddenError):
                await OrderService(db).cancel_order(actor=other, order_id=order_id)

    async def test_cancel_is_idempotent(self):
        order_id = await self._make_order()
        async with self.Session() as db:
            owner = await self._user(db, self.owner_id)
            await OrderService(db).cancel_order(actor=owner, order_id=order_id)
        async with self.Session() as db:
            owner = await self._user(db, self.owner_id)
            again = await OrderService(db).cancel_order(actor=owner, order_id=order_id)
        self.assertEqual(again.refunded, 0)                          # второй раз не возвращаем
        self.assertEqual(await self._balance(self.buyer_id), 2000)

    async def test_completed_order_cannot_be_refunded(self):
        order_id = await self._make_order()
        async with self.Session() as db:
            order = (await db.execute(select(models.Order).filter(models.Order.id == order_id))).scalars().first()
            order.status = "completed"
            await db.commit()
        async with self.Session() as db:
            owner = await self._user(db, self.owner_id)
            with self.assertRaises(ConflictError):
                await OrderService(db).cancel_order(actor=owner, order_id=order_id)


if __name__ == "__main__":
    unittest.main()
