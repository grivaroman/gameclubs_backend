import io
import json
import logging
import unittest

from core.observability import (
    JsonFormatter,
    RedactingFilter,
    SENSITIVE_FIELDS,
    setup_logging,
    setup_sentry,
)


def _make_record(**extra) -> logging.LogRecord:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="event",
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


class JsonFormatterTests(unittest.TestCase):
    def test_emits_valid_json_with_extra_fields(self):
        formatter = JsonFormatter()
        record = _make_record(user_id=42, club_id=7)
        payload = json.loads(formatter.format(record))
        self.assertEqual(payload["level"], "INFO")
        self.assertEqual(payload["msg"], "event")
        self.assertEqual(payload["user_id"], 42)
        self.assertEqual(payload["club_id"], 7)

    def test_handles_exception_info(self):
        formatter = JsonFormatter()
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            import sys

            record = logging.LogRecord(
                name="test", level=logging.ERROR, pathname=__file__, lineno=1,
                msg="failed", args=(), exc_info=sys.exc_info(),
            )
        payload = json.loads(formatter.format(record))
        self.assertIn("RuntimeError", payload["exc_info"])
        self.assertIn("boom", payload["exc_info"])


class RedactingFilterTests(unittest.TestCase):
    def test_masks_sensitive_extra_fields(self):
        filter_ = RedactingFilter()
        record = _make_record(password="hunter2", hashed_password="$2b$...")
        filter_.filter(record)
        self.assertEqual(record.password, "***")  # type: ignore[attr-defined]
        self.assertEqual(record.hashed_password, "***")  # type: ignore[attr-defined]

    def test_masks_sensitive_headers(self):
        filter_ = RedactingFilter()
        record = _make_record(headers={
            "Authorization": "Bearer xyz",
            "Cookie": "access_token=abc",
            "User-Agent": "tests",
        })
        filter_.filter(record)
        headers = record.headers  # type: ignore[attr-defined]
        self.assertEqual(headers["Authorization"], "***")
        self.assertEqual(headers["Cookie"], "***")
        self.assertEqual(headers["User-Agent"], "tests")

    def test_covers_known_sensitive_set(self):
        for name in ("password", "card", "cvv", "secret", "token"):
            self.assertIn(name, SENSITIVE_FIELDS)


class SetupLoggingTests(unittest.TestCase):
    def test_setup_logging_writes_json_when_enabled(self):
        setup_logging(level="INFO", json_format=True)
        logger = logging.getLogger("gameclubs.test")
        buffer = io.StringIO()
        handler = logging.StreamHandler(buffer)
        handler.setFormatter(JsonFormatter())
        handler.addFilter(RedactingFilter())
        logger.handlers = [handler]
        logger.setLevel(logging.INFO)
        logger.info("booking_created", extra={"user_id": 1, "password": "leaked"})
        payload = json.loads(buffer.getvalue().strip())
        self.assertEqual(payload["msg"], "booking_created")
        self.assertEqual(payload["user_id"], 1)
        self.assertEqual(payload["password"], "***")


class SetupSentryTests(unittest.TestCase):
    def test_empty_dsn_returns_false(self):
        self.assertFalse(setup_sentry(None, environment="test"))
        self.assertFalse(setup_sentry("", environment="test"))


if __name__ == "__main__":
    unittest.main()
