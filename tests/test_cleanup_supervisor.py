import asyncio
import logging
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker

import main
import models


class CleanupIterationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(models.Base.metadata.create_all)
        self.Session = sessionmaker(bind=self.engine, class_=models.AsyncSession, expire_on_commit=False)

        self.original_session_local = models.SessionLocal
        models.SessionLocal = self.Session

    async def asyncTearDown(self):
        models.SessionLocal = self.original_session_local
        await self.engine.dispose()

    async def _make_expired_pc(self) -> int:
        async with self.Session() as db:
            user = models.User(email="player@example.com", hashed_password="x", role="user", balance=0)
            db.add(user)
            await db.flush()

            club = models.Club(name="Test Club", address="addr", status="active")
            db.add(club)
            await db.flush()

            pc = models.Computer(
                club_id=club.id,
                number=1,
                category="Standard",
                status="busy",
                current_user_id=user.id,
                end_time=datetime.utcnow() - timedelta(minutes=1),
            )
            db.add(pc)
            await db.flush()

            booking = models.Booking(
                user_id=user.id,
                computer_id=pc.id,
                amount_paid=0,
                status="active",
                starts_at=datetime.utcnow() - timedelta(minutes=10),
                ends_at=pc.end_time,
            )
            db.add(booking)
            await db.commit()
            return pc.id

    async def test_iteration_releases_expired_pc_and_marks_booking(self):
        pc_id = await self._make_expired_pc()
        released = await main.cleanup_expired_sessions_once()
        self.assertEqual(released, 1)

        async with self.Session() as db:
            pc = (await db.execute(select(models.Computer).filter_by(id=pc_id))).scalars().first()
            booking = (await db.execute(select(models.Booking).filter_by(computer_id=pc_id))).scalars().first()
            self.assertEqual(pc.status, "free")
            self.assertIsNone(pc.current_user_id)
            self.assertIsNone(pc.end_time)
            self.assertEqual(booking.status, "expired")

    async def test_iteration_with_no_expired_pcs_is_noop(self):
        released = await main.cleanup_expired_sessions_once()
        self.assertEqual(released, 0)


class CleanupSupervisorTests(unittest.IsolatedAsyncioTestCase):
    async def test_supervisor_keeps_running_after_iteration_exception(self):
        """Падение одной итерации должно быть залогировано и не убить цикл."""
        call_count = 0

        async def flaky_iteration():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("simulated transient failure")
            return 0

        async def fast_sleep(_seconds):
            if call_count >= 2:
                raise asyncio.CancelledError
            return None

        with patch.object(main, "cleanup_expired_sessions_once", flaky_iteration), \
             patch.object(main.asyncio, "sleep", fast_sleep), \
             self.assertLogs("gameclubs", level="ERROR") as captured:
            with self.assertRaises(asyncio.CancelledError):
                await main.cleanup_expired_sessions()

        self.assertEqual(call_count, 2)
        self.assertTrue(any("cleanup_iteration_failed" in msg for msg in captured.output))


if __name__ == "__main__":
    unittest.main()
