"""Refresh-токены мобильного API: login выдаёт access+refresh, /refresh
ротирует, reuse отозванного нукает семью, logout отзывает, невалидный → 401.
"""
import unittest
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.future import select
from sqlalchemy.orm import sessionmaker

import models
from api import router as api_router
from api.auth import get_db as auth_get_db, pwd_context
from config import settings
from core.dependencies import get_db as core_get_db
from core.ratelimit import limiter


class RefreshTokenTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        limiter.reset()
        self.old_csrf = settings.csrf_protection_enabled
        settings.csrf_protection_enabled = False

        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(models.Base.metadata.create_all)
        self.Session = sessionmaker(bind=self.engine, class_=AsyncSession, expire_on_commit=False)
        self.original_session_local = models.SessionLocal
        models.SessionLocal = self.Session

        async with self.Session() as db:
            db.add(models.User(email="p@x.com", hashed_password=pwd_context.hash("password1234"),
                               role="user", is_active=1, balance=0))
            await db.commit()

        app = FastAPI()
        app.include_router(api_router)

        async def override_db():
            async with self.Session() as session:
                yield session

        app.dependency_overrides[core_get_db] = override_db
        app.dependency_overrides[auth_get_db] = override_db
        self.client = TestClient(app)

    async def asyncTearDown(self):
        settings.csrf_protection_enabled = self.old_csrf
        models.SessionLocal = self.original_session_local
        limiter.reset()
        await self.engine.dispose()

    def _login(self):
        return self.client.post("/api/login", json={"email": "p@x.com", "password": "password1234"})

    async def test_login_returns_access_and_refresh(self):
        r = self._login()
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertIn("access_token", body)
        self.assertIn("refresh_token", body)
        # access работает на защищённой ручке
        me = self.client.get("/api/me", headers={"Authorization": f"Bearer {body['access_token']}"})
        self.assertEqual(me.status_code, 200)

    async def test_refresh_rotates_and_reuse_revokes_family(self):
        r1 = self._login().json()["refresh_token"]
        rotated = self.client.post("/api/refresh", json={"refresh_token": r1})
        self.assertEqual(rotated.status_code, 200, rotated.text)
        r2 = rotated.json()["refresh_token"]
        self.assertNotEqual(r1, r2)
        # reuse старого r1 → 401 и отзыв всей семьи
        self.assertEqual(self.client.post("/api/refresh", json={"refresh_token": r1}).status_code, 401)
        # r2 тоже мёртв после reuse
        self.assertEqual(self.client.post("/api/refresh", json={"refresh_token": r2}).status_code, 401)

    async def test_invalid_refresh_401(self):
        self.assertEqual(self.client.post("/api/refresh", json={"refresh_token": "garbage"}).status_code, 401)

    async def test_logout_revokes_refresh(self):
        r = self._login().json()["refresh_token"]
        out = self.client.post("/api/logout", json={"refresh_token": r})
        self.assertEqual(out.status_code, 200)
        self.assertEqual(self.client.post("/api/refresh", json={"refresh_token": r}).status_code, 401)

    # --- change password / logout-all ---
    def _bearer(self, access):
        return {"Authorization": f"Bearer {access}"}

    async def test_change_password_wrong_current_401(self):
        access = self._login().json()["access_token"]
        r = self.client.post("/api/change_password",
                             json={"current_password": "WRONG_pass99", "new_password": "newpassword12"},
                             headers=self._bearer(access))
        self.assertEqual(r.status_code, 401)

    async def test_change_password_revokes_all_sessions(self):
        body = self._login().json()
        access, refresh = body["access_token"], body["refresh_token"]
        r = self.client.post("/api/change_password",
                             json={"current_password": "password1234", "new_password": "newpassword12"},
                             headers=self._bearer(access))
        self.assertEqual(r.status_code, 200, r.text)
        # старый access и refresh мертвы
        self.assertEqual(self.client.get("/api/me", headers=self._bearer(access)).status_code, 401)
        self.assertEqual(self.client.post("/api/refresh", json={"refresh_token": refresh}).status_code, 401)
        # вход по старому паролю не работает, по новому — да
        self.assertEqual(self.client.post("/api/login", json={"email": "p@x.com", "password": "password1234"}).status_code, 401)
        self.assertEqual(self.client.post("/api/login", json={"email": "p@x.com", "password": "newpassword12"}).status_code, 200)

    async def test_logout_all_revokes_sessions(self):
        body = self._login().json()
        access, refresh = body["access_token"], body["refresh_token"]
        self.assertEqual(self.client.get("/api/me", headers=self._bearer(access)).status_code, 200)
        out = self.client.post("/api/logout_all", headers=self._bearer(access))
        self.assertEqual(out.status_code, 200, out.text)
        self.assertEqual(self.client.get("/api/me", headers=self._bearer(access)).status_code, 401)
        self.assertEqual(self.client.post("/api/refresh", json={"refresh_token": refresh}).status_code, 401)

    async def test_expired_refresh_rejected(self):
        r = self._login().json()["refresh_token"]
        # Состариваем токен за пределы срока.
        async with self.Session() as db:
            row = (await db.execute(select(models.RefreshToken))).scalars().first()
            row.expires_at = datetime.utcnow() - timedelta(days=1)
            await db.commit()
        self.assertEqual(self.client.post("/api/refresh", json={"refresh_token": r}).status_code, 401)


if __name__ == "__main__":
    unittest.main()
