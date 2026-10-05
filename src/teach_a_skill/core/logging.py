"""Privacy-safe structured logging for Teach A Skill.

Ensures that sensitive data (keystrokes, screen contents, audio, credentials)
is never inadvertently leaked into local log files or console streams.
"""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

SENSITIVE_KEY_PATTERNS = [
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"credential", re.IGNORECASE),
    re.compile(r"keystroke", re.IGNORECASE),
    re.compile(r"keypress", re.IGNORECASE),
    re.compile(r"raw_audio", re.IGNORECASE),
    re.compile(r"screen_buffer", re.IGNORECASE),
    re.compile(r"screenshot", re.IGNORECASE),
    re.compile(r"api_key", re.IGNORECASE),
]

REDACTED_PLACEHOLDER = "[REDACTED_SENSITIVE]"


def sanitize_data(data: Any, max_depth: int = 5) -> Any:
    """Recursively sanitize data structures to strip sensitive keys and excessive payloads."""
    if max_depth <= 0:
        return "<max_depth_exceeded>"

    if isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            key_str = str(key)
            if any(pattern.search(key_str) for pattern in SENSITIVE_KEY_PATTERNS):
                sanitized[key] = REDACTED_PLACEHOLDER
            else:
                sanitized[key] = sanitize_data(value, max_depth - 1)
        return sanitized

    if isinstance(data, (list, tuple, set)):
        return [sanitize_data(item, max_depth - 1) for item in data]

    if isinstance(data, (bytes, bytearray)):
        return f"<binary_data: {len(data)} bytes>"

    return data


class PrivacySafeLogFormatter(logging.Formatter):
    """Custom formatter that outputs structured JSON logs with sensitive field redaction."""

    def __init__(self, json_format: bool = False) -> None:
        super().__init__()
        self.json_format = json_format

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
        message = record.getMessage()

        # Sanitize extra attributes attached to record
        extra_attrs: dict[str, Any] = {}
        for k, v in record.__dict__.items():
            if k not in (
                "args",
                "asctime",
                "created",
                "exc_info",
                "exc_text",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "msg",
                "name",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "thread",
                "threadName",
            ):
                if any(pattern.search(str(k)) for pattern in SENSITIVE_KEY_PATTERNS):
                    extra_attrs[k] = REDACTED_PLACEHOLDER
                else:
                    extra_attrs[k] = sanitize_data(v)

        if self.json_format:
            log_payload = {
                "timestamp": timestamp,
                "level": record.levelname,
                "logger": record.name,
                "message": message,
            }
            if extra_attrs:
                log_payload["context"] = extra_attrs
            if record.exc_info:
                log_payload["exception"] = self.formatException(record.exc_info)
            return json.dumps(log_payload)

        # Standard console format
        context_str = f" | {json.dumps(extra_attrs)}" if extra_attrs else ""
        exc_str = f"\n{self.formatException(record.exc_info)}" if record.exc_info else ""
        return (
            f"[{timestamp}] [{record.levelname:<7}] [{record.name}] {message}{context_str}{exc_str}"
        )


def setup_logger(
    name: str = "teach_a_skill",
    level: str = "INFO",
    log_file: Optional[str] = None,
    json_format: bool = False,
) -> logging.Logger:
    """Configure and return a privacy-safe logger instance."""
    logger = logging.getLogger(name)
    log_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(log_level)

    # Avoid duplicate handlers if setup is called multiple times
    if not logger.handlers:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(PrivacySafeLogFormatter(json_format=json_format))
        logger.addHandler(console_handler)

        if log_file:
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setFormatter(PrivacySafeLogFormatter(json_format=True))
            logger.addHandler(file_handler)

    return logger


def get_logger(name: str = "teach_a_skill") -> logging.Logger:
    """Retrieve an existing logger or create a default one."""
    return logging.getLogger(name)
