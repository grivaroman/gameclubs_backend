import unittest

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from config import settings
from core.dependencies import get_db
from core.ratelimit import limiter
from core.security import MIN_PASSWORD_LENGTH
from schemas import UserCreate
from web.auth import router as auth_router


async def _fake_db():
    yield None


class PasswordPolicyConstantTests(unittest.TestCase):
    def test_constant_meets_minimum_baseline(self):
        self.assertGreaterEqual(MIN_PASSWORD_LENGTH, 10)


class ApiSchemaPasswordTests(unittest.TestCase):
    def test_short_password_rejected_by_pydantic(self):
        with pytest.raises(ValidationError):
            UserCreate(email="x@example.com", password="a" * (MIN_PASSWORD_LENGTH - 1))

    def test_minimum_length_password_accepted(self):
        user = UserCreate(email="x@example.com", password="a" * MIN_PASSWORD_LENGTH)
        self.assertEqual(len(user.password), MIN_PASSWORD_LENGTH)


class WebFormPasswordTests(unittest.TestCase):
    def setUp(self):
        limiter.reset()
        self.old_csrf = settings.csrf_protection_enabled
        settings.csrf_protection_enabled = False

        app = FastAPI()
        app.include_router(auth_router)
        app.dependency_overrides[get_db] = _fake_db
        self.client = TestClient(app)

    def tearDown(self):
        settings.csrf_protection_enabled = self.old_csrf
        limiter.reset()

    def test_short_password_returns_400(self):
        response = self.client.post(
            "/register",
            data={"email": "new@example.com", "password": "a" * (MIN_PASSWORD_LENGTH - 1)},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Пароль", response.text)


if __name__ == "__main__":
    unittest.main()
