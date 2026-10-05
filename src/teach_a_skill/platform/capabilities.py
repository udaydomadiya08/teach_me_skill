"""Platform capability definitions, capability states, and compatibility manifests for Phase 14."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class CapabilityState(str, Enum):
    """Formal status of an operating system or hardware capability."""

    SUPPORTED = "supported"
    SUPPORTED_WITH_PERMISSION = "supported_with_permission"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"

    def __str__(self) -> str:
        return self.value


class PlatformCapability(str, Enum):
    """Canonical operating system capabilities monitored by Teach A Skill."""

    SCREEN_CAPTURE = "screen_capture"
    MOUSE_INPUT = "mouse_input"
    KEYBOARD_INPUT = "keyboard_input"
    ACCESSIBILITY = "accessibility"
    OCR = "ocr"
    AUDIO_CAPTURE = "audio_capture"
    WINDOW_ENUMERATION = "window_enumeration"
    APPLICATION_ACTIVATION = "application_activation"
    FILESYSTEM_NOTIFICATIONS = "filesystem_notifications"
    SECURE_STORAGE = "secure_storage"
    PROCESS_CONTROL = "process_control"
    CLIPBOARD = "clipboard"
    PERMISSIONS = "permissions"
    MODEL_ACCELERATION = "model_acceleration"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class CapabilityReport:
    """State and diagnostic details for an individual platform capability."""

    capability: PlatformCapability
    state: CapabilityState
    reason: str = ""
    fallback_available: bool = False
    fallback_description: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["capability"] = self.capability.value
        data["state"] = self.state.value
        return data


@dataclass
class PlatformCapabilities:
    """Comprehensive platform capability matrix covering host environment facilities."""

    capabilities: dict[PlatformCapability, CapabilityReport] = field(default_factory=dict)

    def set_capability(
        self,
        capability: PlatformCapability,
        state: CapabilityState,
        reason: str = "",
        fallback_available: bool = False,
        fallback_description: str = "",
    ) -> None:
        self.capabilities[capability] = CapabilityReport(
            capability=capability,
            state=state,
            reason=reason,
            fallback_available=fallback_available,
            fallback_description=fallback_description,
        )

    def get_state(self, capability: PlatformCapability) -> CapabilityState:
        report = self.capabilities.get(capability)
        return report.state if report else CapabilityState.UNAVAILABLE

    def is_usable(self, capability: PlatformCapability) -> bool:
        state = self.get_state(capability)
        return state in (CapabilityState.SUPPORTED, CapabilityState.SUPPORTED_WITH_PERMISSION, CapabilityState.DEGRADED)

    def get_fallback(self, capability: PlatformCapability) -> Optional[str]:
        report = self.capabilities.get(capability)
        if report and report.fallback_available:
            return report.fallback_description
        return None

    def to_dict(self) -> dict[str, Any]:
        return {cap.value: rep.to_dict() for cap, rep in self.capabilities.items()}


@dataclass(frozen=True)
class PlatformCompatibilityManifest:
    """Declared cross-platform compatibility requirements, adaptations, and limits."""

    os_name: str
    minimum_os_version: str
    required_capabilities: list[str]
    optional_capabilities: list[str]
    known_limitations: list[str]
    environment_adaptations: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)
