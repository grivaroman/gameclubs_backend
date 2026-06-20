"""R2: compute_finance считает финансовую сводку SQL-агрегатами, без загрузки
всей истории. Проверяем корректность тоталов и тенант-изоляцию по club_ids.
"""
import unittest
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import models
from web.admin import compute_finance


class ComputeFinanceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(models.Base.metadata.create_all)
        self.Session = sessionmaker(bind=self.engine, class_=AsyncSession, expire_on_commit=False)

        async with self.Session() as db:
            buyer = models.User(email="b@x.com", hashed_password="x", role="user", balance=0)
            db.add(buyer)
            await db.flush()
            mine = models.Club(name="Mine", address="A", status="active")
            other = models.Club(name="Other", address="B", status="active")
            db.add_all([mine, other])
            await db.flush()
            self.mine_id = mine.id
            self.other_id = other.id

            pc = models.Computer(number=1, category="Standard", status="free", club_id=mine.id)
            prod = models.Product(name="Cola", price=300, club_id=mine.id)
            prod_other = models.Product(name="X", price=999, club_id=other.id)
            db.add_all([pc, prod, prod_other])
            await db.flush()

            now = datetime.utcnow()
            db.add(models.Booking(user_id=buyer.id, computer_id=pc.id, amount_paid=500,
                                  status="active", starts_at=now))
            db.add(models.Order(user_id=buyer.id, product_id=prod.id, amount_paid=300,
                                status="new", created_at=now))
            db.add(models.Expense(club_id=mine.id, title="Аренда", amount=200, spent_at=now))
            # чужой клуб — не должен попасть в мою сводку
            db.add(models.Order(user_id=buyer.id, product_id=prod_other.id, amount_paid=999,
                                status="new", created_at=now))
            await db.commit()

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_totals_and_tenant_isolation(self):
        async with self.Session() as db:
            fin = await compute_finance(db, [self.mine_id])
        self.assertEqual(fin["order_revenue"], 300)       # чужие 999 не учтены
        self.assertEqual(fin["booking_revenue"], 500)
        self.assertEqual(fin["revenue_total"], 800)
        self.assertEqual(fin["expense_total"], 200)
        self.assertEqual(fin["profit"], 600)
        self.assertEqual(len(fin["labels"]), 7)
        self.assertEqual(len(fin["income_series"]), 7)
        # сегодняшний доход (последний день окна) = 800
        self.assertEqual(fin["income_series"][-1], 800)
        self.assertEqual(fin["expense_series"][-1], 200)

    async def test_no_clubs_returns_zeroed(self):
        async with self.Session() as db:
            fin = await compute_finance(db, [])
        self.assertEqual(fin["revenue_total"], 0)
        self.assertEqual(fin["income_series"], [0] * 7)


if __name__ == "__main__":
    unittest.main()
