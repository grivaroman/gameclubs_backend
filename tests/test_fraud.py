import json
import unittest
from datetime import datetime

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.future import select
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

import models
from core.fraud import (
    encode_metadata,
    evaluate_admin_top_up,
    evaluate_booking_success,
    evaluate_order_success,
    severity_for_score,
)
from web.auth import create_access_token
from web.user import free_seat


class FraudRuleTests(unittest.TestCase):
    def test_score_maps_to_low_severity(self):
        self.assertEqual(severity_for_score(20), "low")
        self.assertEqual(severity_for_score(49), "low")

    def test_score_maps_to_medium_severity(self):
        self.assertEqual(severity_for_score(50), "medium")
        self.assertEqual(severity_for_score(79), "medium")

    def test_score_maps_to_high_severity(self):
        self.assertEqual(severity_for_score(80), "high")
        self.assertEqual(severity_for_score(100), "high")

    def test_metadata_is_stable_json(self):
        encoded = encode_metadata({"b": 2, "a": "тест"})
        self.assertEqual(json.loads(encoded), {"a": "тест", "b": 2})
        self.assertLess(encoded.index('"a"'), encoded.index('"b"'))

    def test_empty_metadata_is_none(self):
        self.assertIsNone(encode_metadata({}))
        self.assertIsNone(encode_metadata(None))


class FraudDetectionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(models.Base.metadata.create_all)
        self.Session = sessionmaker(bind=self.engine, class_=models.AsyncSession, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def seed_base(self, db):
        user = models.User(email="player@example.com", hashed_password="x", role="user", balance=100_000)
        club = models.Club(name="Club", address="Addr", status="active")
        db.add_all([user, club])
        await db.flush()
        pc = models.Computer(number=1, category="VIP", status="free", club_id=club.id)
        product = models.Product(name="Snack", price=9_000, club_id=club.id)
        package = models.Package(name="VIP", price=19_000, duration_minutes=60, pc_category="VIP", club_id=club.id)
        db.add_all([pc, product, package])
        await db.flush()
        return user, club, pc, product, package

    async def signal_types(self, db):
        res = await db.execute(select(models.FraudSignal.event_type).order_by(models.FraudSignal.event_type))
        return [row[0] for row in res.all()]

    async def test_third_booking_triggers_rapid_signal(self):
        async with self.Session() as db:
            user, _, pc, _, package = await self.seed_base(db)
            db.add_all([
                models.Booking(user_id=user.id, computer_id=pc.id, amount_paid=package.price, starts_at=datetime.utcnow()),
                models.Booking(user_id=user.id, computer_id=pc.id, amount_paid=package.price, starts_at=datetime.utcnow()),
            ])
            await db.flush()

            await evaluate_booking_success(db, user=user, pc=pc, package=package)
            await db.flush()

            self.assertIn("player_rapid_bookings", await self.signal_types(db))

    async def test_fifth_order_triggers_rapid_signal(self):
        async with self.Session() as db:
            user, _, _, product, _ = await self.seed_base(db)
            for _ in range(4):
                db.add(models.Order(user_id=user.id, product_id=product.id, amount_paid=product.price, created_at=datetime.utcnow()))
            await db.flush()

            await evaluate_order_success(db, user=user, product=product)
            await db.flush()

            self.assertIn("player_rapid_orders", await self.signal_types(db))

    async def test_split_booking_amount_triggers_cumulative_signal(self):
        async with self.Session() as db:
            user, _, pc, _, package = await self.seed_base(db)
            db.add(models.Booking(user_id=user.id, computer_id=pc.id, amount_paid=19_000, starts_at=datetime.utcnow()))
            await db.flush()

            await evaluate_booking_success(db, user=user, pc=pc, package=package)
            await db.flush()

            self.assertIn("player_cumulative_booking_spend", await self.signal_types(db))

    async def test_split_order_amount_triggers_cumulative_signal(self):
        async with self.Session() as db:
            user, _, _, product, _ = await self.seed_base(db)
            for _ in range(2):
                db.add(models.Order(user_id=user.id, product_id=product.id, amount_paid=9_000, created_at=datetime.utcnow()))
            await db.flush()

            await evaluate_order_success(db, user=user, product=product)
            await db.flush()

            self.assertIn("player_cumulative_order_spend", await self.signal_types(db))

    async def test_fifth_admin_top_up_becomes_medium_risk(self):
        async with self.Session() as db:
            user, _, _, _, _ = await self.seed_base(db)
            admin = models.User(email="admin@example.com", hashed_password="x", role="superadmin", balance=0)
            db.add(admin)
            await db.flush()
            for _ in range(4):
                db.add(models.FraudSignal(
                    actor_user_id=admin.id,
                    actor_role=admin.role,
                    subject_user_id=user.id,
                    event_type="admin_top_up_observed",
                    severity="low",
                    score=25,
                    reason="seed",
                    metadata_json=encode_metadata({"amount": 1_000}),
                ))
            await db.flush()

            await evaluate_admin_top_up(db, admin=admin, target_user=user, amount=1_000)
            await db.flush()

            res = await db.execute(
                select(models.FraudSignal.score).filter(
                    models.FraudSignal.actor_user_id == admin.id,
                    models.FraudSignal.event_type == "admin_top_up_observed",
                    models.FraudSignal.reason == "Ручное пополнение баланса администратором",
                )
            )
            self.assertEqual(res.scalar_one(), 55)

    async def test_split_admin_top_up_amount_triggers_cumulative_signal(self):
        async with self.Session() as db:
            user, _, _, _, _ = await self.seed_base(db)
            admin = models.User(email="admin2@example.com", hashed_password="x", role="superadmin", balance=0)
            db.add(admin)
            await db.flush()
            for _ in range(3):
                db.add(models.FraudSignal(
                    actor_user_id=admin.id,
                    actor_role=admin.role,
                    subject_user_id=user.id,
                    event_type="admin_top_up_observed",
                    severity="low",
                    score=25,
                    reason="seed",
                    metadata_json=encode_metadata({"amount": 25_000}),
                ))
            await db.flush()

            await evaluate_admin_top_up(db, admin=admin, target_user=user, amount=25_000)
            await db.flush()

            self.assertIn("admin_cumulative_top_up_risk", await self.signal_types(db))

    def request_for_user(self, user: models.User) -> Request:
        token = create_access_token(user.email)
        return Request({
            "type": "http",
            "method": "POST",
            "path": "/free_seat/1",
            "query_string": b"",
            "headers": [(b"cookie", f"access_token={token}".encode())],
        })

    async def test_admin_free_seat_route_creates_override_signal(self):
        async with self.Session() as db:
            player, club, pc, _, _ = await self.seed_base(db)
            admin = models.User(email="owner@example.com", hashed_password="x", role="owner", balance=0)
            db.add(admin)
            await db.flush()
            club.owner_id = admin.id
            pc.status = "busy"
            pc.current_user_id = player.id
            db.add(models.Booking(user_id=player.id, computer_id=pc.id, status="active", amount_paid=1_000))
            await db.commit()

            response = await free_seat(self.request_for_user(admin), pc.id, db)
            await db.flush()

            self.assertEqual(response["status"], "success")
            self.assertIn("admin_pc_status_override", await self.signal_types(db))

    async def test_player_free_seat_route_does_not_create_admin_override_signal(self):
        async with self.Session() as db:
            player, _, pc, _, _ = await self.seed_base(db)
            pc.status = "busy"
            pc.current_user_id = player.id
            db.add(models.Booking(user_id=player.id, computer_id=pc.id, status="active", amount_paid=1_000))
            await db.commit()

            response = await free_seat(self.request_for_user(player), pc.id, db)
            await db.flush()

            self.assertEqual(response["status"], "success")
            self.assertNotIn("admin_pc_status_override", await self.signal_types(db))


if __name__ == "__main__":
    unittest.main()
