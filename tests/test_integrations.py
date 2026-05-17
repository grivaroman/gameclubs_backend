import socket
import unittest
from unittest.mock import patch

from config import settings
from core.integrations import validate_integration_url


def addrinfo(ip: str):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))]


class IntegrationUrlValidationTests(unittest.TestCase):
    def setUp(self):
        self.old_allow_private = settings.allow_private_integration_hosts
        settings.allow_private_integration_hosts = False

    def tearDown(self):
        settings.allow_private_integration_hosts = self.old_allow_private

    def test_rejects_non_http_scheme(self):
        self.assertIn("http://", validate_integration_url("ftp://example.com"))

    def test_rejects_credentials_in_url(self):
        self.assertIn("нельзя", validate_integration_url("https://user:pass@example.com"))

    @patch("core.integrations.socket.getaddrinfo", return_value=addrinfo("127.0.0.1"))
    def test_rejects_loopback_host(self, _):
        self.assertIn("localhost", validate_integration_url("https://one-c.example.com"))

    @patch("core.integrations.socket.getaddrinfo", return_value=addrinfo("192.168.1.10"))
    def test_rejects_private_host_by_default(self, _):
        self.assertIn("Приватные", validate_integration_url("https://one-c.example.com"))

    @patch("core.integrations.socket.getaddrinfo", return_value=addrinfo("192.168.1.10"))
    def test_allows_private_host_when_enabled(self, _):
        settings.allow_private_integration_hosts = True
        self.assertIsNone(validate_integration_url("https://one-c.example.com"))

    @patch("core.integrations.socket.getaddrinfo", return_value=addrinfo("93.184.216.34"))
    def test_allows_public_host(self, _):
        self.assertIsNone(validate_integration_url("https://example.com"))


if __name__ == "__main__":
    unittest.main()
