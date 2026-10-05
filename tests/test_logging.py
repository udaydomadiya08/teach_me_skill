"""Tests for privacy-safe logging and redaction."""

import json
import logging

from teach_a_skill.core.logging import (
    REDACTED_PLACEHOLDER,
    PrivacySafeLogFormatter,
    sanitize_data,
)


def test_sanitize_sensitive_keys():
    payload = {
        "user": "test_user",
        "password": "secret_password_123",
        "api_key": "sk-1234567890",
        "token": "bearer abc",
        "keystroke_buffer": "typing my credit card",
        "nested": {
            "credential_id": "xyz",
            "safe_counter": 42,
        },
    }

    sanitized = sanitize_data(payload)
    assert sanitized["user"] == "test_user"
    assert sanitized["password"] == REDACTED_PLACEHOLDER
    assert sanitized["api_key"] == REDACTED_PLACEHOLDER
    assert sanitized["token"] == REDACTED_PLACEHOLDER
    assert sanitized["keystroke_buffer"] == REDACTED_PLACEHOLDER
    assert sanitized["nested"]["credential_id"] == REDACTED_PLACEHOLDER
    assert sanitized["nested"]["safe_counter"] == 42


def test_sanitize_binary_data():
    raw_bytes = b"\x00" * 1024
    sanitized = sanitize_data(raw_bytes)
    assert "<binary_data: 1024 bytes>" in sanitized


def test_privacy_safe_json_formatter():
    formatter = PrivacySafeLogFormatter(json_format=True)
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="User action registered",
        args=(),
        exc_info=None,
    )
    record.password = "supersecret"
    record.step = 3

    output = formatter.format(record)
    parsed = json.loads(output)

    assert parsed["level"] == "INFO"
    assert parsed["message"] == "User action registered"
    assert parsed["context"]["password"] == REDACTED_PLACEHOLDER
    assert parsed["context"]["step"] == 3
