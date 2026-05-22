import asyncio
import unittest

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from core.ratelimit import (
    LOGIN_LIMIT,
    REGISTER_LIMIT,
    RateLimit,
    InMemoryRateLimiter,
    enforce_rate_limit,
    limiter,
)


class RateLimiterCoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_allows_up_to_limit_then_blocks(self):
        rl = InMemoryRateLimiter()
        cfg = RateLimit(limit=3, window_seconds=60)
        results = [await rl.check("k", cfg) for _ in range(3)]
        self.assertTrue(all(ok for ok, _ in results))

        ok, retry = await rl.check("k", cfg)
        self.assertFalse(ok)
        self.assertGreaterEqual(retry, 1)

    async def test_separate_keys_dont_share_quota(self):
        rl = InMemoryRateLimiter()
        cfg = RateLimit(limit=1, window_seconds=60)
        ok_a, _ = await rl.check("a", cfg)
        ok_b, _ = await rl.check("b", cfg)
        self.assertTrue(ok_a and ok_b)

    async def test_expired_hits_are_evicted(self):
        rl = InMemoryRateLimiter()
        cfg = RateLimit(limit=1, window_seconds=0)
        await rl.check("k", cfg)
        await asyncio.sleep(0.01)
        ok, _ = await rl.check("k", cfg)
        self.assertTrue(ok)


class RateLimitEndpointTests(unittest.TestCase):
    def setUp(self):
        limiter.reset()
        app = FastAPI()

        @app.post("/login")
        async def login(request: Request):
            limited = await enforce_rate_limit(request, "login", LOGIN_LIMIT)
            if limited:
                return limited
            return {"ok": True}

        @app.post("/register")
        async def register(request: Request):
            limited = await enforce_rate_limit(request, "register", REGISTER_LIMIT)
            if limited:
                return limited
            return {"ok": True}

        self.client = TestClient(app)

    def tearDown(self):
        limiter.reset()

    def test_login_returns_429_after_limit(self):
        for _ in range(LOGIN_LIMIT.limit):
            self.assertEqual(self.client.post("/login").status_code, 200)
        response = self.client.post("/login")
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response.headers)

    def test_register_has_independent_bucket(self):
        for _ in range(LOGIN_LIMIT.limit):
            self.client.post("/login")
        # Login исчерпан, но register со своим квотным ведром.
        self.assertEqual(self.client.post("/register").status_code, 200)

    def test_blocked_response_carries_retry_after_seconds(self):
        for _ in range(LOGIN_LIMIT.limit):
            self.client.post("/login")
        response = self.client.post("/login")
        retry = int(response.headers["Retry-After"])
        self.assertGreater(retry, 0)
        self.assertLessEqual(retry, LOGIN_LIMIT.window_seconds + 1)


if __name__ == "__main__":
    unittest.main()
