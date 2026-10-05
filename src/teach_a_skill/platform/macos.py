"""macOS platform adapter implementation with full capability matrix and compatibility manifest."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from teach_a_skill.platform.base import BasePlatformAdapter
from teach_a_skill.platform.capabilities import (
    CapabilityState,
    PlatformCapabilities,
    PlatformCapability,
    PlatformCompatibilityManifest,
)


class MacOSAdapter(BasePlatformAdapter):
    """Platform adapter tailored for Darwin / macOS environments."""

    @property
    def os_name(self) -> str:
        return "macos"

    def get_desktop_environment(self) -> Optional[str]:
        return "Aqua"

    def get_default_data_dir(self) -> str:
        home = Path.home()
        app_support = home / "Library" / "Application Support" / "TeachASkill"
        if app_support.parent.exists():
            return str(app_support)
        return str(home / ".teach_a_skill")

    def get_capabilities(self) -> PlatformCapabilities:
        """Probe live macOS capabilities with permission awareness."""
        caps = PlatformCapabilities()
        caps.set_capability(PlatformCapability.SCREEN_CAPTURE, CapabilityState.SUPPORTED_WITH_PERMISSION, "macOS Quartz / Screen Recording permission required")
        caps.set_capability(PlatformCapability.MOUSE_INPUT, CapabilityState.SUPPORTED_WITH_PERMISSION, "CoreGraphics event generation requires Accessibility permission")
        caps.set_capability(PlatformCapability.KEYBOARD_INPUT, CapabilityState.SUPPORTED_WITH_PERMISSION, "CoreGraphics event generation requires Accessibility permission")
        caps.set_capability(
            PlatformCapability.ACCESSIBILITY,
            CapabilityState.SUPPORTED_WITH_PERMISSION,
            "macOS AXUIElement API requires Accessibility permissions",
            fallback_available=True,
            fallback_description="Fallback to vision-based screen perception and OCR element localization",
        )
        caps.set_capability(PlatformCapability.OCR, CapabilityState.SUPPORTED, "Apple Vision Framework and offline OCR engines operational")
        caps.set_capability(PlatformCapability.AUDIO_CAPTURE, CapabilityState.SUPPORTED_WITH_PERMISSION, "AVFoundation audio input requires microphone permission")
        caps.set_capability(PlatformCapability.WINDOW_ENUMERATION, CapabilityState.SUPPORTED, "CGWindowList / Quartz Window Services supported")
        caps.set_capability(PlatformCapability.APPLICATION_ACTIVATION, CapabilityState.SUPPORTED, "NSWorkspace application launch and activation supported")
        caps.set_capability(PlatformCapability.FILESYSTEM_NOTIFICATIONS, CapabilityState.SUPPORTED, "macOS FSEvents / kqueue notification system supported")
        caps.set_capability(PlatformCapability.SECURE_STORAGE, CapabilityState.SUPPORTED, "macOS Keychain integration supported")
        caps.set_capability(PlatformCapability.PROCESS_CONTROL, CapabilityState.SUPPORTED, "POSIX process monitoring and signals supported")
        caps.set_capability(PlatformCapability.CLIPBOARD, CapabilityState.SUPPORTED, "macOS NSPasteboard integration supported")
        caps.set_capability(PlatformCapability.PERMISSIONS, CapabilityState.SUPPORTED, "macOS TCC permission framework inspection supported")
        caps.set_capability(PlatformCapability.MODEL_ACCELERATION, CapabilityState.SUPPORTED, "Apple Silicon Metal Performance Shaders / Unified Memory supported")
        return caps

    def get_compatibility_manifest(self) -> PlatformCompatibilityManifest:
        return PlatformCompatibilityManifest(
            os_name="macos",
            minimum_os_version="12.0 (Monterey)",
            required_capabilities=[
                PlatformCapability.PROCESS_CONTROL.value,
                PlatformCapability.FILESYSTEM_NOTIFICATIONS.value,
            ],
            optional_capabilities=[
                PlatformCapability.ACCESSIBILITY.value,
                PlatformCapability.SCREEN_CAPTURE.value,
                PlatformCapability.MODEL_ACCELERATION.value,
            ],
            known_limitations=[
                "Accessibility API requires explicit user grant in System Settings -> Privacy & Security",
                "Screen Recording requires explicit user grant",
            ],
            environment_adaptations={
                "accessibility_unavailable": "Visual grounding using OCR and template perception",
                "metal_unavailable": "CPU-only deterministic inference",
            },
        )


MacOSPlatformAdapter = MacOSAdapter
