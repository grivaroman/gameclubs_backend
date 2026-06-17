"""Security-фиксы JSON API:

  * #2 /api/* — Bearer-only: cookie-аутентификация не принимается, поэтому
    CSRF-карваут для /api/ безопасен (cookie-only запрос → 401, даже без Origin).
  * #3 rate-limit на /api/auth/login и /register.
  * #5 tenancy в POST /api/notifications/{id}/read (IDOR → 403).
"""
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import models
from api import router as api_router
from api.auth import get_db as auth_get_db
from config import settings
from core.dependencies import get_db as core_get_db
from core.ratelimit import LOGIN_LIMIT, limiter
from core.security import CSRFMiddleware
from web.auth import create_access_token


class ApiSecurityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        limiter.reset()
        self.old_csrf = settings.csrf_protection_enabled
        self.old_origin = settings.public_origin
        settings.csrf_protection_enabled = True   # CSRF включён — проверяем карваут
        settings.public_origin = None

        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(models.Base.metadata.create_all)
        self.Session = sessionmaker(bind=self.engine, class_=AsyncSession, expire_on_commit=False)
        self.original_session_local = models.SessionLocal
        models.SessionLocal = self.Session

        async with self.Session() as db:
            player = models.User(email="player@x.com", hashed_password="x", role="user", is_active=1, balance=0)
            owner_a = models.User(email="owner-a@x.com", hashed_password="x", role="owner", is_active=1, balance=0)
            owner_b = models.User(email="owner-b@x.com", hashed_password="x", role="owner", is_active=1, balance=0)
            db.add_all([player, owner_a, owner_b])
            await db.flush()
            self.player_email = player.email
            self.owner_a_email = owner_a.email
            self.owner_b_email = owner_b.email

            club_b = models.Club(name="Club B", address="B", owner_id=owner_b.id, status="active")
            db.add(club_b)
            await db.flush()
            note = models.Notification(kind="booking", club_id=club_b.id, title="t", message="m")
            db.add(note)
            await db.flush()
            self.note_id = note.id
            await db.commit()

        app = FastAPI()
        app.add_middleware(CSRFMiddleware)
        app.include_router(api_router)

        async def override_db():
            async with self.Session() as session:
                yield session

        app.dependency_overrides[core_get_db] = override_db
        app.dependency_overrides[auth_get_db] = override_db
        self.client = TestClient(app)

    async def asyncTearDown(self):
        settings.csrf_protection_enabled = self.old_csrf
        settings.public_origin = self.old_origin
        models.SessionLocal = self.original_session_local
        limiter.reset()
        await self.engine.dispose()

    def _bearer(self, email):
        return {"Authorization": f"Bearer {create_access_token(email)}"}

    # --- #2 Bearer-only / CSRF carve-out safe ---
    async def test_api_me_with_bearer_ok(self):
        r = self.client.get("/api/me", headers=self._bearer(self.player_email))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["email"], self.player_email)

    async def test_api_me_with_cookie_only_is_401(self):
        # Cookie больше НЕ аутентифицирует API — иначе CSRF-карваут был бы дырой.
        self.client.cookies.set("access_token", create_access_token(self.player_email))
        r = self.client.get("/api/me")
        self.client.cookies.clear()
        self.assertEqual(r.status_code, 401)

    async def test_api_money_action_with_cookie_only_rejected(self):
        # CSRF пропускает /api/, но cookie-only buy_product отбивается на auth-слое.
        self.client.cookies.set("access_token", create_access_token(self.player_email))
        r = self.client.post("/api/buy_product/1")  # без Origin, без Bearer
        self.client.cookies.clear()
        self.assertEqual(r.status_code, 401)

    # --- #3 rate-limit ---
    async def test_login_rate_limited(self):
        codes = []
        for _ in range(LOGIN_LIMIT.limit + 1):
            resp = self.client.post("/api/login", json={"email": "nobody@x.com", "password": "bad"})
            codes.append(resp.status_code)
        self.assertIn(429, codes)            # лимит сработал
        self.assertEqual(codes[-1], 429)     # последний запрос отбит

    # --- #5 notification tenancy (IDOR) ---
    async def test_player_cannot_mark_notification(self):
        r = self.client.post(f"/api/notifications/{self.note_id}/read", headers=self._bearer(self.player_email))
        self.assertEqual(r.status_code, 403)

    async def test_other_club_owner_cannot_mark_notification(self):
        r = self.client.post(f"/api/notifications/{self.note_id}/read", headers=self._bearer(self.owner_a_email))
        self.assertEqual(r.status_code, 403)

    async def test_owning_club_admin_can_mark_notification(self):
        r = self.client.post(f"/api/notifications/{self.note_id}/read", headers=self._bearer(self.owner_b_email))
        self.assertEqual(r.status_code, 200, r.text)


if __name__ == "__main__":
    unittest.main()
