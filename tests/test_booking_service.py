"""Money/logic-фиксы BookingService (аггрегаторный поток заявок):

  * M1 — нельзя подтвердить заявку на занятый ПК (анти-овербукинг).
  * M2 — protухшие pending-заявки авто-отклоняются с возвратом депозита.
  * M3 — валидация окна времени + гарантированный конечный end_time на confirm.
"""
import unittest
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.future import select
from sqlalchemy.orm import sessionmaker

import models
from config import settings
from core.services.booking_service import BookingService
from core.services.exceptions import ConflictError, ValidationError


class BookingServiceMoneyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(models.Base.metadata.create_all)
        self.Session = sessionmaker(bind=self.engine, class_=AsyncSession, expire_on_commit=False)
        self.original_session_local = models.SessionLocal
        models.SessionLocal = self.Session

        async with self.Session() as db:
            owner = models.User(email="owner@x.com", hashed_password="x", role="owner", is_active=1, balance=0)
            p1 = models.User(email="p1@x.com", hashed_password="x", role="user", is_active=1, balance=5000)
            p2 = models.User(email="p2@x.com", hashed_password="x", role="user", is_active=1, balance=5000)
            db.add_all([owner, p1, p2])
            await db.flush()
            self.owner_id, self.p1_id, self.p2_id = owner.id, p1.id, p2.id

            club = models.Club(name="C", address="A", owner_id=owner.id, status="active",
                               booking_mode="prepaid", booking_deposit=1000)
            db.add(club)
            await db.flush()
            self.club_id = club.id
            pc = models.Computer(number=1, category="Standard", status="free", club_id=club.id)
            db.add(pc)
            await db.flush()
            self.pc_id = pc.id
            await db.commit()

    async def asyncTearDown(self):
        models.SessionLocal = self.original_session_local
        await self.engine.dispose()

    async def _owner(self, db):
        return (await db.execute(select(models.User).filter(models.User.id == self.owner_id))).scalars().first()

    async def _balance(self, user_id):
        async with self.Session() as db:
            u = (await db.execute(select(models.User).filter(models.User.id == user_id))).scalars().first()
            return u.balance

    # --- M1: анти-овербукинг ---
    async def test_confirm_second_request_on_busy_pc_rejected(self):
        async with self.Session() as db:
            r1 = await BookingService(db).create_booking_request(user_id=self.p1_id, pc_id=self.pc_id)
            r2 = await BookingService(db).create_booking_request(user_id=self.p2_id, pc_id=self.pc_id)
        async with self.Session() as db:
            owner = await self._owner(db)
            await BookingService(db).confirm_request(actor=owner, booking_id=r1.booking_id)  # ok
        async with self.Session() as db:
            owner = await self._owner(db)
            with self.assertRaises(ConflictError):   # ПК занят → нельзя подтвердить вторую
                await BookingService(db).confirm_request(actor=owner, booking_id=r2.booking_id)
        # Активная бронь на ПК ровно одна.
        async with self.Session() as db:
            actives = (await db.execute(
                select(models.Booking).filter(
                    models.Booking.computer_id == self.pc_id, models.Booking.status == "active"
                )
            )).scalars().all()
            self.assertEqual(len(actives), 1)

    # --- M3: валидация времени ---
    async def test_ends_at_before_start_rejected(self):
        async with self.Session() as db:
            with self.assertRaises(ValidationError):
                await BookingService(db).create_booking_request(
                    user_id=self.p1_id, pc_id=self.pc_id, ends_at=datetime.utcnow() - timedelta(hours=1)
                )

    async def test_duration_over_max_rejected(self):
        too_long = datetime.utcnow() + timedelta(minutes=settings.max_booking_duration_minutes + 120)
        async with self.Session() as db:
            with self.assertRaises(ValidationError):
                await BookingService(db).create_booking_request(
                    user_id=self.p1_id, pc_id=self.pc_id, ends_at=too_long
                )

    async def test_start_in_past_rejected(self):
        async with self.Session() as db:
            with self.assertRaises(ValidationError):
                await BookingService(db).create_booking_request(
                    user_id=self.p1_id, pc_id=self.pc_id, starts_at=datetime.utcnow() - timedelta(hours=2)
                )

    async def test_confirm_without_ends_at_sets_finite_end_time(self):
        async with self.Session() as db:
            r = await BookingService(db).create_booking_request(user_id=self.p1_id, pc_id=self.pc_id)
        async with self.Session() as db:
            owner = await self._owner(db)
            await BookingService(db).confirm_request(actor=owner, booking_id=r.booking_id)
        async with self.Session() as db:
            booking = (await db.execute(select(models.Booking).filter(models.Booking.id == r.booking_id))).scalars().first()
            pc = (await db.execute(select(models.Computer).filter(models.Computer.id == self.pc_id))).scalars().first()
            self.assertIsNotNone(booking.ends_at)     # M3: конечное время проставлено
            self.assertIsNotNone(pc.end_time)
            self.assertEqual(pc.status, "busy")

    # --- M2: протухание заявок с возвратом депозита ---
    async def test_stale_request_expired_and_deposit_refunded(self):
        async with self.Session() as db:
            r = await BookingService(db).create_booking_request(user_id=self.p1_id, pc_id=self.pc_id)
        self.assertEqual(await self._balance(self.p1_id), 4000)   # депозит 1000 списан

        # Состариваем заявку за пределы TTL.
        async with self.Session() as db:
            booking = (await db.execute(select(models.Booking).filter(models.Booking.id == r.booking_id))).scalars().first()
            booking.starts_at = datetime.utcnow() - timedelta(minutes=settings.booking_request_ttl_minutes + 60)
            await db.commit()

        async with self.Session() as db:
            expired = await BookingService(db).expire_stale_requests()
        self.assertEqual(expired, 1)
        self.assertEqual(await self._balance(self.p1_id), 5000)   # депозит возвращён

        async with self.Session() as db:
            booking = (await db.execute(select(models.Booking).filter(models.Booking.id == r.booking_id))).scalars().first()
            self.assertEqual(booking.status, "rejected")

    async def test_recent_request_not_expired(self):
        async with self.Session() as db:
            r = await BookingService(db).create_booking_request(user_id=self.p1_id, pc_id=self.pc_id)
        async with self.Session() as db:
            expired = await BookingService(db).expire_stale_requests()
        self.assertEqual(expired, 0)
        self.assertEqual(await self._balance(self.p1_id), 4000)   # депозит всё ещё удержан


if __name__ == "__main__":
    unittest.main()
