import unittest

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

from config import settings
from core.security import CSRFMiddleware, SecurityHeadersMiddleware


class SecurityMiddlewareTests(unittest.TestCase):
    def setUp(self):
        self.old_csrf_enabled = settings.csrf_protection_enabled
        self.old_public_origin = settings.public_origin
        self.old_trusted_origins = settings.csrf_trusted_origins
        settings.csrf_protection_enabled = True
        settings.public_origin = None
        settings.csrf_trusted_origins = ""

        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)
        app.add_middleware(CSRFMiddleware)

        @app.get("/health")
        async def health():
            return PlainTextResponse("ok")

        @app.post("/mutate")
        async def mutate():
            return PlainTextResponse("changed")

        self.client = TestClient(app)

    def tearDown(self):
        settings.csrf_protection_enabled = self.old_csrf_enabled
        settings.public_origin = self.old_public_origin
        settings.csrf_trusted_origins = self.old_trusted_origins

    def test_security_headers_are_added(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")

    def test_same_origin_post_is_allowed(self):
        response = self.client.post("/mutate", headers={"Origin": "http://testserver"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "changed")

    def test_cross_origin_post_is_rejected(self):
        response = self.client.post("/mutate", headers={"Origin": "https://evil.example"})
        self.assertEqual(response.status_code, 403)

    def test_missing_origin_post_is_rejected(self):
        response = self.client.post("/mutate")
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
