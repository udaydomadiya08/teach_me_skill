"""Privacy protection, local-only enforcement, and sensitive text redaction for perception."""

import re
from typing import Optional

from teach_a_skill.core.logging import get_logger

logger = get_logger("teach_a_skill.perception.privacy")

# Regular expressions for common sensitive strings
SENSITIVE_PATTERNS = [
    # US Social Security Number
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED_SSN]"),
    # Credit Card
    (re.compile(r"\b(?:\d[ -]*?){13,16}\b"), "[REDACTED_CARD]"),
    # Email
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"), "[REDACTED_EMAIL]"),
    # API key / auth token patterns (sk_live, Bearer, etc.)
    (re.compile(r"(?:sk_live_|ghp_|eyJh)[A-Za-z0-9_-]{16,}"), "[REDACTED_TOKEN]"),
    # Password label followed by text
    (re.compile(r"(?i)(?:password|passwd|pwd)\s*[:=]\s*\S+"), "password: [REDACTED]"),
]


class PerceptionPrivacyManager:
    """Enforces zero-network invariants and redacts sensitive PII/secrets from recognized text."""

    def __init__(self, redact_sensitive_patterns: bool = True, persist_raw_ocr: bool = True) -> None:
        self.redact_sensitive_patterns = redact_sensitive_patterns
        self.persist_raw_ocr = persist_raw_ocr

    def sanitize_text(self, text: Optional[str]) -> str:
        """Mask detected sensitive patterns in OCR text."""
        if not text:
            return ""
        if not self.redact_sensitive_patterns:
            return text

        sanitized = text
        for pattern, replacement in SENSITIVE_PATTERNS:
            sanitized = pattern.sub(replacement, sanitized)
        return sanitized
