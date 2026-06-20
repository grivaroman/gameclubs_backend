"""GET /api/me/transactions — история баланса игрока (ledger)."""
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import models
from api.auth import _create_access_token
from api.me import router as me_router
from core.dependencies import get_db as core_get_db


class MeTransactionsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(models.Base.metadata.create_all)
        self.Session = sessionmaker(bind=self.engine, class_=AsyncSession, expire_on_commit=False)
        self.original_session_local = models.SessionLocal
        models.SessionLocal = self.Session

        async with self.Session() as db:
            user = models.User(email="p@x.com", hashed_password="x", role="user", is_active=1, balance=1500)
            other = models.User(email="o@x.com", hashed_password="x", role="user", is_active=1, balance=0)
            db.add_all([user, other])
            await db.flush()
            self.email = user.email
            db.add_all([
                models.BalanceTransaction(user_id=user.id, amount=2000, balance_after=2000,
                                          kind="kaspi_test_top_up", reason="Пополнение"),
                models.BalanceTransaction(user_id=user.id, amount=-500, balance_after=1500,
                                          kind="booking_debit", reason="Бронь"),
                # чужая транзакция — не должна попасть в выдачу
                models.BalanceTransaction(user_id=other.id, amount=999, balance_after=999, kind="admin_top_up"),
            ])
            await db.commit()

        app = FastAPI()
        app.include_router(me_router, prefix="/api")

        async def override_db():
            async with self.Session() as session:
                yield session

        app.dependency_overrides[core_get_db] = override_db
        self.client = TestClient(app)

    async def asyncTearDown(self):
        models.SessionLocal = self.original_session_local
        await self.engine.dispose()

    async def test_transactions_requires_auth(self):
        self.assertEqual(self.client.get("/api/me/transactions").status_code, 401)

    async def test_transactions_returns_only_own_ledger(self):
        headers = {"Authorization": f"Bearer {_create_access_token(self.email)}"}
        r = self.client.get("/api/me/transactions", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(len(body), 2)                       # только свои
        kinds = {t["kind"] for t in body}
        self.assertEqual(kinds, {"kaspi_test_top_up", "booking_debit"})
        self.assertTrue(all("balance_after" in t and "amount" in t for t in body))


if __name__ == "__main__":
    unittest.main()
