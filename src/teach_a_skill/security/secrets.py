"""High-assurance SecretDetector and redaction engine for Phase 14."""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class SecretMatch:
    """Detected secret instance with pattern classification and location."""

    secret_type: str
    redacted_preview: str
    start: int
    end: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SecretDetector:
    """Detects passwords, API keys, private keys, authentication tokens, and credentials."""

    PATTERNS: dict[str, re.Pattern] = {
        "AWS_ACCESS_KEY": re.compile(r"\b(AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}\b"),
        "GITHUB_TOKEN": re.compile(r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,255}\b"),
        "STRIPE_API_KEY": re.compile(r"\b[sr]k_(live|test)_[0-9a-zA-Z]{24,99}\b"),
        "SLACK_TOKEN": re.compile(r"\bxox[baprs]-[0-9]{10,13}-[0-9]{10,13}[a-zA-Z0-9-]*\b"),
        "PRIVATE_KEY": re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----[\s\S]+?-----END (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
        "JWT_TOKEN": re.compile(r"\beyJ[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*\b"),
        "DB_CONNECTION": re.compile(r"\b(postgres|postgresql|mysql|mongodb|redis)://[a-zA-Z0-9_]+:[^@\s]+@[a-zA-Z0-9.-]+:[0-9]+/[a-zA-Z0-9_]+\b"),
        "BEARER_TOKEN": re.compile(r"(?i)\bbearer\s+([a-zA-Z0-9_\-\.]{20,})\b"),
        "GENERIC_SECRET_ASSIGNMENT": re.compile(r"(?i)(api[_-]?key|access[_-]?token|auth[_-]?token|secret[_-]?key|password|passwd|pwd)\s*[:=]\s*['\"]([^'\"]{6,})['\"]"),
    }

    SENSITIVE_KEY_NAMES = {
        "password",
        "passwd",
        "pwd",
        "secret",
        "token",
        "auth",
        "credential",
        "private_key",
        "api_key",
        "access_token",
        "session_id",
        "cookie",
    }

    @classmethod
    def scan_text(cls, text: str) -> list[SecretMatch]:
        """Scan raw string for secret matches across known regex signatures."""
        if not text:
            return []

        matches: list[SecretMatch] = []
        for stype, pat in cls.PATTERNS.items():
            for m in pat.finditer(text):
                val = m.group(0)
                # Obfuscate preview
                preview = val[:4] + "..." + val[-3:] if len(val) > 10 else "[SECRET]"
                matches.append(
                    SecretMatch(
                        secret_type=stype,
                        redacted_preview=preview,
                        start=m.start(),
                        end=m.end(),
                    )
                )
        return matches

    @classmethod
    def redact_text(cls, text: str) -> str:
        """Replace all secret substrings in text with '[REDACTED_SECRET]' markers."""
        if not text:
            return ""

        redacted = text
        for stype, pat in cls.PATTERNS.items():
            redacted = pat.sub(f"[REDACTED_{stype}]", redacted)
        return redacted

    @classmethod
    def redact_structure(cls, data: Any) -> Any:
        """Recursively redact dictionary keys and values matching secret criteria."""
        if isinstance(data, dict):
            clean: dict[str, Any] = {}
            for k, v in data.items():
                k_str = str(k).lower()
                if any(sens in k_str for sens in cls.SENSITIVE_KEY_NAMES):
                    clean[k] = "[REDACTED]"
                elif isinstance(v, str):
                    clean[k] = cls.redact_text(v)
                else:
                    clean[k] = cls.redact_structure(v)
            return clean
        elif isinstance(data, list):
            return [cls.redact_structure(item) for item in data]
        elif isinstance(data, str):
            return cls.redact_text(data)
        return data

    @classmethod
    def estimate_entropy(cls, text: str) -> float:
        """Calculate Shannon entropy to assist in detecting high-randomness secret strings."""
        if not text:
            return 0.0
        entropy = 0.0
        length = len(text)
        counts: dict[str, int] = {}
        for c in text:
            counts[c] = counts.get(c, 0) + 1
        for count in counts.values():
            p = count / length
            entropy -= p * math.log2(p)
        return round(entropy, 2)
