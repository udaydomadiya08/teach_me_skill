"""Sensitive input handling, application exclusions, and privacy filters.

Protects confidential user data (passwords, credentials, private apps) during
demonstration recording through configurable policies and application barriers.
"""

import re
from enum import Enum
from typing import Optional

from teach_a_skill.recorder.keyboard import KeyEventPayload


class SensitiveInputPolicy(str, Enum):
    """Policy for capturing keyboard input data."""

    RECORD = "RECORD"  # Record keys and characters as demonstrated
    MASK = "MASK"  # Obfuscate characters with '*' but preserve timing/count
    SUPPRESS = "SUPPRESS"  # Completely omit keyboard character inputs

    def __str__(self) -> str:
        return self.value


class PrivacyFilter:
    """Evaluates active window, application name, and user privacy toggles."""

    DEFAULT_EXCLUDED_APPS = {
        "1password",
        "bitwarden",
        "keepass",
        "keepassxc",
        "keychain access",
        "lastpass",
        "signal",
        "telegram",
        "whatsapp",
        "authenticator",
    }

    DEFAULT_EXCLUDED_WINDOW_PATTERNS = [
        re.compile(r"password", re.IGNORECASE),
        re.compile(r"credentials?", re.IGNORECASE),
        re.compile(r"sign in", re.IGNORECASE),
        re.compile(r"log in", re.IGNORECASE),
        re.compile(r"authenticat(or|ion)", re.IGNORECASE),
        re.compile(r"private browsing", re.IGNORECASE),
        re.compile(r"incognito", re.IGNORECASE),
    ]

    def __init__(
        self,
        input_policy: SensitiveInputPolicy = SensitiveInputPolicy.RECORD,
        excluded_apps: Optional[set[str]] = None,
        excluded_window_patterns: Optional[list[re.Pattern]] = None,
    ) -> None:
        self.input_policy = input_policy
        self.excluded_apps = {a.lower() for a in (excluded_apps or self.DEFAULT_EXCLUDED_APPS)}
        self.excluded_window_patterns = (
            excluded_window_patterns or self.DEFAULT_EXCLUDED_WINDOW_PATTERNS
        )
        self._manual_privacy_mode: bool = False

    @property
    def manual_privacy_mode(self) -> bool:
        return self._manual_privacy_mode

    def set_manual_privacy_mode(self, enabled: bool) -> None:
        """Toggle manual privacy mode (e.g. via hotkey)."""
        self._manual_privacy_mode = enabled

    def is_context_sensitive(
        self,
        app_name: Optional[str] = None,
        window_title: Optional[str] = None,
    ) -> bool:
        """Determine if current application or window title is classified as sensitive."""
        if self._manual_privacy_mode:
            return True

        if app_name:
            clean_app = app_name.strip().lower()
            if clean_app in self.excluded_apps:
                return True

        if window_title:
            for pattern in self.excluded_window_patterns:
                if pattern.search(window_title):
                    return True

        return False

    def filter_key_payload(
        self,
        payload: KeyEventPayload,
        app_name: Optional[str] = None,
        window_title: Optional[str] = None,
    ) -> Optional[KeyEventPayload]:
        """Apply privacy filtering to keyboard payload."""
        is_sensitive = self.is_context_sensitive(app_name, window_title)

        # In sensitive context or under SUPPRESS policy, drop character keys
        if is_sensitive or self.input_policy == SensitiveInputPolicy.SUPPRESS:
            # Special navigation keys like Enter, Tab, Esc, BackSpace can still be recorded
            # if they do not contain typed text
            if payload.key in (
                "Return",
                "Enter",
                "Tab",
                "Escape",
                "BackSpace",
                "ArrowUp",
                "ArrowDown",
                "ArrowLeft",
                "ArrowRight",
            ):
                return payload
            return None

        if self.input_policy == SensitiveInputPolicy.MASK:
            # Mask single alphanumeric characters while preserving shortcuts and modifiers
            if len(payload.key) == 1 and not payload.is_shortcut:
                return KeyEventPayload(
                    key="*",
                    action=payload.action,
                    code=payload.code,
                    modifiers=payload.modifiers,
                    is_shortcut=False,
                    shortcut_string=None,
                    text="*" if payload.text else None,
                )

        return payload

    def should_suppress_screen_capture(
        self,
        app_name: Optional[str] = None,
        window_title: Optional[str] = None,
    ) -> bool:
        """Check whether screen capture should be blanked or suppressed."""
        return self.is_context_sensitive(app_name, window_title)
