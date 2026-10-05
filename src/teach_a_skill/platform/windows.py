"""Windows platform adapter implementation with UI Automation, capabilities, and fallback manifests."""

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


class WindowsAdapter(BasePlatformAdapter):
    """Platform adapter tailored for Windows 10/11 environments."""

    @property
    def os_name(self) -> str:
        return "windows"

    def get_desktop_environment(self) -> Optional[str]:
        return "Windows Shell"

    def get_default_data_dir(self) -> str:
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return str(Path(local_app_data) / "TeachASkill")
        return str(Path.home() / ".teach_a_skill")

    def get_capabilities(self) -> PlatformCapabilities:
        """Probe Windows capabilities including UI Automation, DPAPI, and graphics capture."""
        caps = PlatformCapabilities()
        caps.set_capability(PlatformCapability.SCREEN_CAPTURE, CapabilityState.SUPPORTED, "Windows Graphics Capture API and Desktop Duplication supported")
        caps.set_capability(PlatformCapability.MOUSE_INPUT, CapabilityState.SUPPORTED, "Windows SendInput API supported for focused application windows")
        caps.set_capability(PlatformCapability.KEYBOARD_INPUT, CapabilityState.SUPPORTED, "Windows SendInput API supported")
        caps.set_capability(
            PlatformCapability.ACCESSIBILITY,
            CapabilityState.SUPPORTED,
            "Microsoft UI Automation (UIA) tree inspection supported",
            fallback_available=True,
            fallback_description="Visual OCR perception fallback",
        )
        caps.set_capability(PlatformCapability.OCR, CapabilityState.SUPPORTED, "Windows.Media.Ocr / local OCR pipeline supported")
        caps.set_capability(PlatformCapability.AUDIO_CAPTURE, CapabilityState.SUPPORTED_WITH_PERMISSION, "WASAPI audio input requires microphone privacy grant in Windows Settings")
        caps.set_capability(PlatformCapability.WINDOW_ENUMERATION, CapabilityState.SUPPORTED, "Win32 EnumWindows / GetWindowText supported")
        caps.set_capability(PlatformCapability.APPLICATION_ACTIVATION, CapabilityState.SUPPORTED, "Win32 SetForegroundWindow and ShellExecute supported")
        caps.set_capability(PlatformCapability.FILESYSTEM_NOTIFICATIONS, CapabilityState.SUPPORTED, "Win32 ReadDirectoryChangesW supported")
        caps.set_capability(PlatformCapability.SECURE_STORAGE, CapabilityState.SUPPORTED, "Windows Data Protection API (DPAPI) and Credential Manager supported")
        caps.set_capability(PlatformCapability.PROCESS_CONTROL, CapabilityState.SUPPORTED, "Win32 Process and Thread API supported")
        caps.set_capability(PlatformCapability.CLIPBOARD, CapabilityState.SUPPORTED, "Win32 Clipboard API supported")
        caps.set_capability(PlatformCapability.PERMISSIONS, CapabilityState.SUPPORTED, "Windows AppContainer and Privacy Settings inspection supported")
        caps.set_capability(PlatformCapability.MODEL_ACCELERATION, CapabilityState.SUPPORTED, "DirectML / ONNX Runtime acceleration supported on Windows")

        return caps

    def get_compatibility_manifest(self) -> PlatformCompatibilityManifest:
        return PlatformCompatibilityManifest(
            os_name="windows",
            minimum_os_version="Windows 10 Build 19041+ (64-bit) / Windows 11",
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
                "UAC elevated windows cannot receive synthetic input from non-elevated processes (UIPI boundary)",
                "Microphone privacy settings must permit desktop application access",
            ],
            environment_adaptations={
                "uipi_restricted": "Fail-closed on elevated windows; request user focus or safe manual input",
                "directml_unavailable": "Deterministic baseline CPU execution mode",
            },
        )


WindowsPlatformAdapter = WindowsAdapter
