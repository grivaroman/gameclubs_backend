"""Логирование и Sentry для CyberBooking.

Логи — структурные, JSON в проде, human-readable в dev. Чувствительные поля
(`password`, `hashed_password`, `card*`, `Authorization`, `Cookie`) маскируются
перед форматированием — на случай если их передадут в `extra=`.

Sentry поднимается только если задан `SENTRY_DSN`. Без зависимостей-фантомов:
если sentry-sdk не установлен, поднятие логирует warning и продолжает работу.
"""
import json
import logging
import logging.config
import sys
from typing import Any, Iterable

SENSITIVE_FIELDS = frozenset({
    "password",
    "hashed_password",
    "card",
    "card_number",
    "cvv",
    "secret",
    "token",
})
SENSITIVE_HEADERS = frozenset({"authorization", "cookie", "set-cookie", "x-pc-token"})

_STANDARD_RECORD_KEYS = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "asctime",
})


def _mask(value: Any) -> str:
    return "***"


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        for field in SENSITIVE_FIELDS:
            if hasattr(record, field):
                setattr(record, field, _mask(getattr(record, field)))
        headers = getattr(record, "headers", None)
        if isinstance(headers, dict):
            record.headers = {  # type: ignore[attr-defined]
                k: (_mask(v) if k.lower() in SENSITIVE_HEADERS else v)
                for k, v in headers.items()
            }
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _STANDARD_RECORD_KEYS or key.startswith("_"):
                continue
            payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(level: str = "INFO", json_format: bool = False) -> None:
    formatter: dict[str, Any] = (
        {"()": JsonFormatter}
        if json_format
        else {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}
    )
    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {"redact": {"()": RedactingFilter}},
        "formatters": {"default": formatter},
        "handlers": {
            "stdout": {
                "class": "logging.StreamHandler",
                "stream": sys.stdout,
                "formatter": "default",
                "filters": ["redact"],
            },
        },
        "root": {"handlers": ["stdout"], "level": level},
        "loggers": {
            "uvicorn": {"handlers": ["stdout"], "level": level, "propagate": False},
            "uvicorn.access": {"handlers": ["stdout"], "level": level, "propagate": False},
            "uvicorn.error": {"handlers": ["stdout"], "level": level, "propagate": False},
        },
    })


def _strip_sentry_pii(event: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any]:
    request = event.get("request") or {}
    headers = request.get("headers") or {}
    if isinstance(headers, dict):
        request["headers"] = {
            k: (_mask(v) if k.lower() in SENSITIVE_HEADERS else v)
            for k, v in headers.items()
        }
        event["request"] = request
    user = event.get("user")
    if isinstance(user, dict):
        user.pop("ip_address", None)
        user.pop("email", None)
        event["user"] = user
    return event


def setup_sentry(dsn: str | None, environment: str, release: str | None = None) -> bool:
    if not dsn:
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.starlette import StarletteIntegration
        from sentry_sdk.integrations.fastapi import FastApiIntegration
    except ImportError:
        logging.getLogger(__name__).warning(
            "sentry_dsn_set_but_sdk_missing",
            extra={"hint": "pip install 'sentry-sdk[fastapi]'"},
        )
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=release,
        send_default_pii=False,
        traces_sample_rate=0.1,
        integrations=[StarletteIntegration(), FastApiIntegration()],
        before_send=_strip_sentry_pii,
    )
    return True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


__all__: Iterable[str] = (
    "JsonFormatter",
    "RedactingFilter",
    "get_logger",
    "setup_logging",
    "setup_sentry",
)
