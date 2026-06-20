from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import PlainTextResponse
from passlib.context import CryptContext
from starlette.middleware.base import BaseHTTPMiddleware

from config import settings

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
MIN_PASSWORD_LENGTH = 10

# Единый bcrypt-контекст для всего приложения — не создавать CryptContext
# по месту (web/auth, api/auth, main раньше дублировали его).
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def split_csv(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def normalize_origin(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def request_origin(request: Request) -> str:
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip()
    host = request.headers.get("host", request.url.netloc)
    return f"{scheme.lower()}://{host.lower()}"


def allowed_origins_for_request(request: Request) -> set[str]:
    origins = {request_origin(request)}
    if settings.public_origin:
        normalized = normalize_origin(settings.public_origin)
        if normalized:
            origins.add(normalized)
    origins.update(filter(None, (normalize_origin(item) for item in split_csv(settings.csrf_trusted_origins))))
    return origins


def is_same_site_request(request: Request) -> bool:
    origin = normalize_origin(request.headers.get("origin"))
    if not origin:
        origin = normalize_origin(request.headers.get("referer"))
    return bool(origin and origin in allowed_origins_for_request(request))


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if settings.csrf_protection_enabled and request.method in UNSAFE_METHODS:
            # /api/ endpoints use Bearer tokens — CSRF via cookies cannot be set
            # cross-origin with custom headers, so no CSRF check needed there.
            if not request.url.path.startswith("/api/") and not is_same_site_request(request):
                return PlainTextResponse("CSRF validation failed", status_code=403)
        return await call_next(request)
