import unittest

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config import settings
from core.security import CSRFMiddleware


class KaspiTestPaymentGateTests(unittest.TestCase):
    """Эндпоинт kaspi_test_payment должен быть закрыт по умолчанию и недоступен,
    пока флаг `enable_kaspi_test_payment` не выставлен явно."""

    def setUp(self):
        self.old_flag = settings.enable_kaspi_test_payment
        self.old_csrf = settings.csrf_protection_enabled
        self.old_origin = settings.public_origin
        settings.csrf_protection_enabled = True
        settings.public_origin = None

        # Импортируем после установки флагов окружения, чтобы роутер видел актуальные настройки.
        from web.user import router as user_router

        app = FastAPI()
        app.add_middleware(CSRFMiddleware)
        app.include_router(user_router)
        self.client = TestClient(app)

    def tearDown(self):
        settings.enable_kaspi_test_payment = self.old_flag
        settings.csrf_protection_enabled = self.old_csrf
        settings.public_origin = self.old_origin

    def test_disabled_by_default(self):
        self.assertFalse(settings.enable_kaspi_test_payment)

    def test_returns_404_when_flag_off(self):
        settings.enable_kaspi_test_payment = False
        response = self.client.post(
            "/payments/kaspi/test",
            data={"amount": "5000"},
            headers={"Origin": "http://testserver"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json().get("status"), "error")

    def test_production_validator_forbids_enabling_kaspi_test(self):
        """В production-окружении выставленный флаг должен валиться на старте."""
        from config import DEFAULT_SECRET_KEY, Settings

        with pytest.raises(ValueError) as exc:
            Settings(
                environment="production",
                secret_key="x" * 64,
                cookie_secure=True,
                public_origin="https://example.com",
                allowed_hosts="example.com",
                auto_create_db_schema=False,
                enable_kaspi_test_payment=True,
            )
        self.assertIn("ENABLE_KASPI_TEST_PAYMENT", str(exc.value))
        assert DEFAULT_SECRET_KEY  # sanity, чтобы импорт точно использовался


if __name__ == "__main__":
    unittest.main()
