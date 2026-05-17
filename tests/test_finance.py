import unittest
from datetime import datetime
from types import SimpleNamespace

from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker

import models
from core.finance import InsufficientBalanceError, credit_user_balance, debit_user_balance
from web.admin import build_finance_summary


class FinanceSummaryTests(unittest.TestCase):
    def test_builds_revenue_expense_and_profit(self):
        today = datetime.utcnow()
        orders = [
            SimpleNamespace(amount_paid=1500, product=SimpleNamespace(price=9999), created_at=today),
            SimpleNamespace(amount_paid=0, product=SimpleNamespace(price=700), created_at=today),
        ]
        bookings = [SimpleNamespace(amount_paid=3000, starts_at=today)]
        expenses = [SimpleNamespace(amount=1200, spent_at=today)]

        summary = build_finance_summary(orders, bookings, expenses)

        self.assertEqual(summary["order_revenue"], 2200)
        self.assertEqual(summary["booking_revenue"], 3000)
        self.assertEqual(summary["expense_total"], 1200)
        self.assertEqual(summary["profit"], 4000)
        self.assertEqual(len(summary["labels"]), 7)
        self.assertEqual(summary["income_series"][-1], 5200)
        self.assertEqual(summary["expense_series"][-1], 1200)


class BalanceLedgerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(models.Base.metadata.create_all)
        self.Session = sessionmaker(bind=self.engine, class_=models.AsyncSession, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_credit_and_debit_record_balance_transactions(self):
        async with self.Session() as db:
            admin = models.User(email="admin@example.com", hashed_password="x", role="superadmin", balance=0)
            user = models.User(email="player@example.com", hashed_password="x", role="user", balance=1000)
            db.add_all([admin, user])
            await db.flush()

            await credit_user_balance(db, user=user, actor=admin, amount=500, kind="admin_top_up")
            await debit_user_balance(db, user=user, amount=300, kind="order_debit")
            await db.flush()

            res = await db.execute(select(models.BalanceTransaction).order_by(models.BalanceTransaction.id))
            transactions = res.scalars().all()

            self.assertEqual(user.balance, 1200)
            self.assertEqual([tx.amount for tx in transactions], [500, -300])
            self.assertEqual([tx.balance_after for tx in transactions], [1500, 1200])
            self.assertEqual(transactions[0].actor_user_id, admin.id)

    async def test_debit_rejects_insufficient_balance_without_mutation(self):
        async with self.Session() as db:
            user = models.User(email="player2@example.com", hashed_password="x", role="user", balance=100)
            db.add(user)
            await db.flush()

            with self.assertRaises(InsufficientBalanceError):
                await debit_user_balance(db, user=user, amount=101, kind="order_debit")

            res = await db.execute(select(models.BalanceTransaction))
            self.assertEqual(user.balance, 100)
            self.assertEqual(res.scalars().all(), [])


if __name__ == "__main__":
    unittest.main()
