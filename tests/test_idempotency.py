"""Идемпотентность денежных действий по Idempotency-Key: повторный запрос с тем
же ключом не списывает дважды; разные ключи — разные операции; ошибка не
кэшируется (ключ освобождается для повтора); без ключа — обычное поведение.
"""
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.future import select
from sqlalchemy.orm import sessionmaker

import models
from api import router as api_router
from core.api_tokens import create_mobile_access_token
from core.dependencies import get_db as core_get_db


class IdempotencyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(models.Base.metadata.create_all)
        self.Session = sessionmaker(bind=self.engine, class_=AsyncSession, expire_on_commit=False)
        self.original_session_local = models.SessionLocal
        models.SessionLocal = self.Session

        async with self.Session() as db:
            user = models.User(email="p@x.com", hashed_password="x", role="user", is_active=1, balance=1000)
            db.add(user)
            await db.flush()
            self.email = user.email
            club = models.Club(name="C", address="A", status="active")
            db.add(club)
            await db.flush()
            product = models.Product(name="Cola", price=400, club_id=club.id)
            db.add(product)
            await db.flush()
            self.product_id = product.id
            await db.commit()

        app = FastAPI()
        app.include_router(api_router)

        async def override_db():
            async with self.Session() as session:
                yield session

        app.dependency_overrides[core_get_db] = override_db
        self.client = TestClient(app)

    async def asyncTearDown(self):
        models.SessionLocal = self.original_session_local
        await self.engine.dispose()

    def _headers(self, key=None):
        h = {"Authorization": f"Bearer {create_mobile_access_token(self.email)}"}
        if key:
            h["Idempotency-Key"] = key
        return h

    def _buy(self, key=None):
        return self.client.post(f"/api/buy_product/{self.product_id}", headers=self._headers(key))

    async def _balance(self):
        async with self.Session() as db:
            u = (await db.execute(select(models.User).filter(models.User.email == self.email))).scalars().first()
            return u.balance

    async def test_same_key_charges_once(self):
        r1 = self._buy("K1")
        self.assertEqual(r1.status_code, 200, r1.text)
        self.assertEqual(await self._balance(), 600)
        # повтор с тем же ключом — кэшированный ответ, без второго списания
        r2 = self._buy("K1")
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json(), r1.json())
        self.assertEqual(await self._balance(), 600)

    async def test_different_keys_charge_separately(self):
        self._buy("A")
        self._buy("B")
        self.assertEqual(await self._balance(), 200)   # 1000 - 400 - 400

    async def test_error_is_not_cached_and_key_freed(self):
        self._buy("A")
        self._buy("B")                                  # balance → 200
        first = self._buy("C")                          # 200 < 400 → 402
        self.assertEqual(first.status_code, 402)
        # ключ C освобождён: повтор снова реально выполняется (а не отдаёт кэш)
        again = self._buy("C")
        self.assertEqual(again.status_code, 402)

    async def test_no_key_is_normal_behavior(self):
        self.assertEqual(self._buy().status_code, 200)
        self.assertEqual(self._buy().status_code, 200)
        self.assertEqual(await self._balance(), 200)    # без ключа списывается каждый раз


if __name__ == "__main__":
    unittest.main()
