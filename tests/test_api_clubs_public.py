"""Публичная витрина клубов /api/clubs не должна раскрывать PII игроков:
кто (current_user_id) сидит за ПК. Отдаём только статус и end_time.
"""
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import models
from api.clubs import get_db as clubs_get_db, router as clubs_router


class PublicClubComputersTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(models.Base.metadata.create_all)
        self.Session = sessionmaker(bind=self.engine, class_=AsyncSession, expire_on_commit=False)
        self.original_session_local = models.SessionLocal
        models.SessionLocal = self.Session

        async with self.Session() as db:
            player = models.User(email="p@x.com", hashed_password="x", role="user", is_active=1)
            db.add(player)
            await db.flush()
            club = models.Club(name="C", address="A", status="active")
            db.add(club)
            await db.flush()
            self.club_id = club.id
            self.player_id = player.id
            db.add(models.Computer(number=1, category="Standard", status="busy",
                                   club_id=club.id, current_user_id=player.id))
            await db.commit()

        app = FastAPI()
        app.include_router(clubs_router, prefix="/api")

        async def override_db():
            async with self.Session() as session:
                yield session

        app.dependency_overrides[clubs_get_db] = override_db
        self.client = TestClient(app)

    async def asyncTearDown(self):
        models.SessionLocal = self.original_session_local
        await self.engine.dispose()

    async def test_computers_endpoint_hides_current_user_id(self):
        r = self.client.get(f"/api/clubs/{self.club_id}/computers")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(len(body), 1)
        pc = body[0]
        self.assertEqual(pc["status"], "busy")
        self.assertNotIn("current_user_id", pc)   # PII не утекает
        self.assertIn("end_time", pc)             # время освобождения остаётся (UX)


if __name__ == "__main__":
    unittest.main()
