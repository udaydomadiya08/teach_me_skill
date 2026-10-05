"""Canonical Permission Manager and Least-Privilege Enforcer for Phase 14."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional

from teach_a_skill.core.errors import TeachSkillError


class PermissionType(str, Enum):
    """Canonical operating-system and subsystem permissions."""

    SCREEN_CAPTURE = "screen_capture"
    ACCESSIBILITY = "accessibility"
    MICROPHONE = "microphone"
    INPUT_CONTROL = "input_control"
    FILESYSTEM = "filesystem"
    CLIPBOARD = "clipboard"
    PROCESS_CONTROL = "process_control"
    NETWORK = "network"

    def __str__(self) -> str:
        return self.value


class PermissionState(str, Enum):
    """Evaluation state of an explicit permission grant."""

    UNKNOWN = "unknown"
    GRANTED = "granted"
    DENIED = "denied"
    RESTRICTED = "restricted"
    NOT_SUPPORTED = "not_supported"

    def __str__(self) -> str:
        return self.value


class PermissionDeniedError(TeachSkillError):
    """Raised when an operation is requested without required permission grant."""
    pass


@dataclass
class PermissionManager:
    """Manages least-privilege permission grants, fail-closed defaults, and state inspection."""

    _grants: dict[PermissionType, PermissionState] = field(default_factory=dict)
    _audit_log: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Fail-closed safe defaults: NETWORK is strictly DENIED by default
        self._grants.setdefault(PermissionType.NETWORK, PermissionState.DENIED)
        self._grants.setdefault(PermissionType.FILESYSTEM, PermissionState.GRANTED)
        self._grants.setdefault(PermissionType.PROCESS_CONTROL, PermissionState.GRANTED)
        # Hardware-touching permissions default to UNKNOWN or DENIED until explicitly granted
        for p in (PermissionType.SCREEN_CAPTURE, PermissionType.ACCESSIBILITY, PermissionType.MICROPHONE, PermissionType.INPUT_CONTROL, PermissionType.CLIPBOARD):
            self._grants.setdefault(p, PermissionState.UNKNOWN)

    def check_permission(self, permission: PermissionType) -> PermissionState:
        """Query current state of a permission."""
        return self._grants.get(permission, PermissionState.UNKNOWN)

    def require_permission(self, permission: PermissionType, operation: str) -> None:
        """Enforce fail-closed permission check. Raises PermissionDeniedError if not granted."""
        state = self.check_permission(permission)
        if state != PermissionState.GRANTED:
            explanation = self._explain_failure(permission, state, operation)
            raise PermissionDeniedError(
                f"Operation '{operation}' denied: permission '{permission.value}' is {state.value.upper()}. {explanation}"
            )

    def grant_permission(self, permission: PermissionType, reason: str = "Operator explicit grant") -> None:
        """Explicitly grant a permission."""
        self._grants[permission] = PermissionState.GRANTED
        self._audit_log.append({
            "action": "GRANT",
            "permission": permission.value,
            "reason": reason,
        })

    def revoke_permission(self, permission: PermissionType, reason: str = "Operator explicit revocation") -> None:
        """Revoke a permission, returning state to DENIED."""
        self._grants[permission] = PermissionState.DENIED
        self._audit_log.append({
            "action": "REVOKE",
            "permission": permission.value,
            "reason": reason,
        })

    def _explain_failure(self, permission: PermissionType, state: PermissionState, operation: str) -> str:
        """Provide clear user-facing guidance on denied permission."""
        if permission == PermissionType.NETWORK:
            return "Teach A Skill operates under a strict Local-Only / Offline policy. Network access is disabled by default."
        elif permission == PermissionType.ACCESSIBILITY:
            return "Accessibility access is required to inspect semantic UI elements. Please grant permission in OS Privacy & Security settings."
        elif permission == PermissionType.SCREEN_CAPTURE:
            return "Screen recording permission is required to capture visual UI state for grounding."
        elif permission == PermissionType.INPUT_CONTROL:
            return "Input control permission is required to simulate physical mouse or keyboard events."
        elif permission == PermissionType.MICROPHONE:
            return "Microphone permission is required for real-time speech-to-text demonstration capture."
        return f"Please ensure '{permission.value}' is authorized for this operation."

    def to_dict(self) -> dict[str, str]:
        return {p.value: state.value for p, state in self._grants.items()}
