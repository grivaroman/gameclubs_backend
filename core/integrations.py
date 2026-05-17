import base64
import ipaddress
import os
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urljoin, urlparse

import models
from config import settings


@dataclass
class IntegrationCheckResult:
    ok: bool
    status: str


def build_integration_url(integration: models.ClubIntegration) -> str:
    base_url = (integration.base_url or "").strip()
    health_path = (integration.health_path or "/").strip() or "/"
    if not base_url.endswith("/"):
        base_url += "/"
    return urljoin(base_url, health_path.lstrip("/"))


def validate_integration_url(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return "URL интеграции должен начинаться с http:// или https://"
    if not parsed.hostname:
        return "В URL интеграции не найден host"
    if parsed.username or parsed.password:
        return "Логин и пароль нельзя передавать в URL"

    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return "Host интеграции не найден"

    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified:
            return "Нельзя подключать интеграцию к localhost или служебным адресам"
        if ip.is_private and not settings.allow_private_integration_hosts:
            return "Приватные адреса 1С запрещены настройкой сервера"
    return None


def build_auth_header(integration: models.ClubIntegration) -> str | None:
    secret = os.getenv((integration.secret_env_key or "").strip())
    if not secret:
        return None
    username = (integration.username or "").strip()
    if username:
        raw = f"{username}:{secret}".encode("utf-8")
        return f"Basic {base64.b64encode(raw).decode('ascii')}"
    return f"Bearer {secret}"


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def check_integration(integration: models.ClubIntegration, timeout: int = 10) -> IntegrationCheckResult:
    if not integration.base_url:
        return IntegrationCheckResult(False, "Не указан URL интеграции")

    integration_url = build_integration_url(integration)
    validation_error = validate_integration_url(integration_url)
    if validation_error:
        return IntegrationCheckResult(False, validation_error)

    request = urllib.request.Request(integration_url, method="GET")
    auth_header = build_auth_header(integration)
    if auth_header:
        request.add_header("Authorization", auth_header)
    request.add_header("Accept", "application/json, text/plain, */*")

    try:
        opener = urllib.request.build_opener(NoRedirectHandler)
        with opener.open(request, timeout=timeout) as response:
            status = response.getcode()
    except urllib.error.HTTPError as exc:
        return IntegrationCheckResult(False, f"HTTP {exc.code}")
    except urllib.error.URLError as exc:
        return IntegrationCheckResult(False, f"Ошибка подключения: {exc.reason}")
    except TimeoutError:
        return IntegrationCheckResult(False, "Таймаут подключения")

    if 200 <= status < 300:
        return IntegrationCheckResult(True, f"OK HTTP {status}")
    return IntegrationCheckResult(False, f"HTTP {status}")


def touch_integration_status(integration: models.ClubIntegration, status: str) -> None:
    integration.last_status = status
    integration.last_checked_at = datetime.utcnow()
    integration.updated_at = datetime.utcnow()
