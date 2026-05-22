import unittest

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.future import select
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

import models
from web.admin import complete_order, issue_computer_ws_token, update_computer_status
from web.auth import create_access_token


class TenantIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(models.Base.metadata.create_all)
        self.Session = sessionmaker(bind=self.engine, class_=AsyncSession, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    def request_for_user(self, user: models.User) -> Request:
        token = create_access_token(user.email)
        return Request({
            "type": "http",
            "method": "POST",
            "path": "/admin",
            "query_string": b"",
            "headers": [(b"cookie", f"access_token={token}".encode())],
        })

    async def seed_two_tenants(self, db: AsyncSession):
        owner_a = models.User(email="owner-a@example.com", hashed_password="x", role="owner", balance=0)
        owner_b = models.User(email="owner-b@example.com", hashed_password="x", role="owner", balance=0)
        db.add_all([owner_a, owner_b])
        await db.flush()

        club_a = models.Club(name="Club A", address="A", owner_id=owner_a.id, status="active")
        club_b = models.Club(name="Club B", address="B", owner_id=owner_b.id, status="active")
        db.add_all([club_a, club_b])
        await db.flush()

        pc_b = models.Computer(number=1, category="Standard", status="free", club_id=club_b.id)
        product_b = models.Product(name="Water", price=500, club_id=club_b.id)
        db.add_all([pc_b, product_b])
        await db.flush()

        order_b = models.Order(user_id=owner_b.id, product_id=product_b.id, amount_paid=500, status="new")
        db.add(order_b)
        await db.commit()
        return owner_a, owner_b, club_a, club_b, pc_b, product_b, order_b

    async def test_owner_cannot_update_other_club_pc_status(self):
        async with self.Session() as db:
            owner_a, _, _, _, pc_b, _, _ = await self.seed_two_tenants(db)

            response = await update_computer_status(
                self.request_for_user(owner_a),
                pc_id=pc_b.id,
                status="busy",
                db=db,
            )
            await db.refresh(pc_b)

            self.assertEqual(response.status_code, 403)
            self.assertEqual(pc_b.status, "free")

    async def test_owner_cannot_issue_ws_token_for_other_club_pc(self):
        async with self.Session() as db:
            owner_a, _, _, _, pc_b, _, _ = await self.seed_two_tenants(db)

            response = await issue_computer_ws_token(pc_b.id, self.request_for_user(owner_a), db)
            await db.refresh(pc_b)

            self.assertEqual(response.status_code, 403)
            self.assertIsNone(pc_b.ws_token_hash)

    async def test_owner_cannot_complete_other_club_order(self):
        async with self.Session() as db:
            owner_a, _, _, _, _, _, order_b = await self.seed_two_tenants(db)

            response = await complete_order(order_b.id, self.request_for_user(owner_a), db)
            refreshed = await db.execute(select(models.Order).filter(models.Order.id == order_b.id))
            order = refreshed.scalars().one()

            self.assertEqual(response.status_code, 403)
            self.assertEqual(order.status, "new")


if __name__ == "__main__":
    unittest.main()
