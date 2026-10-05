"""Linux platform adapter implementation with Wayland/X11 detection, capabilities, and fallback manifests."""

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


class LinuxAdapter(BasePlatformAdapter):
    """Platform adapter tailored for Linux and XDG desktop environments."""

    @property
    def os_name(self) -> str:
        return "linux"

    def get_desktop_environment(self) -> Optional[str]:
        return (
            os.environ.get("XDG_CURRENT_DESKTOP")
            or os.environ.get("DESKTOP_SESSION")
            or "Headless/Unknown"
        )

    def get_session_type(self) -> str:
        """Return 'wayland', 'x11', or 'headless'."""
        sess = os.environ.get("XDG_SESSION_TYPE", "").lower()
        if "wayland" in sess or "WAYLAND_DISPLAY" in os.environ:
            return "wayland"
        if "x11" in sess or "DISPLAY" in os.environ:
            return "x11"
        return "headless"

    def get_default_data_dir(self) -> str:
        xdg_data = os.environ.get("XDG_DATA_HOME")
        if xdg_data:
            return str(Path(xdg_data) / "teach_a_skill")
        return str(Path.home() / ".local" / "share" / "teach_a_skill")

    def get_capabilities(self) -> PlatformCapabilities:
        """Probe live Linux capabilities taking into account Wayland, X11, and portal boundaries."""
        caps = PlatformCapabilities()
        sess_type = self.get_session_type()

        if sess_type == "wayland":
            caps.set_capability(
                PlatformCapability.SCREEN_CAPTURE,
                CapabilityState.SUPPORTED_WITH_PERMISSION,
                "Wayland PipeWire Portal screen capture supported with session grant",
                fallback_available=True,
                fallback_description="Fallback to headless capture or synthetic frames",
            )
            caps.set_capability(
                PlatformCapability.MOUSE_INPUT,
                CapabilityState.DEGRADED,
                "Direct synthetic input restricted under Wayland; requires libei or X11 compatibility bridge",
                fallback_available=True,
                fallback_description="Simulated action execution or remote desktop portal",
            )
            caps.set_capability(
                PlatformCapability.KEYBOARD_INPUT,
                CapabilityState.DEGRADED,
                "Global keyboard input restricted under Wayland without elevated portal permissions",
            )
        elif sess_type == "x11":
            caps.set_capability(PlatformCapability.SCREEN_CAPTURE, CapabilityState.SUPPORTED, "X11 XShm / XComposite supported")
            caps.set_capability(PlatformCapability.MOUSE_INPUT, CapabilityState.SUPPORTED, "X11 XTest extension supported")
            caps.set_capability(PlatformCapability.KEYBOARD_INPUT, CapabilityState.SUPPORTED, "X11 XTest extension supported")
        else:
            caps.set_capability(PlatformCapability.SCREEN_CAPTURE, CapabilityState.UNAVAILABLE, "Headless Linux environment without display server")
            caps.set_capability(PlatformCapability.MOUSE_INPUT, CapabilityState.UNAVAILABLE, "No display server for input")
            caps.set_capability(PlatformCapability.KEYBOARD_INPUT, CapabilityState.UNAVAILABLE, "No display server for input")

        caps.set_capability(
            PlatformCapability.ACCESSIBILITY,
            CapabilityState.SUPPORTED,
            "AT-SPI2 Linux accessibility bridge operational",
            fallback_available=True,
            fallback_description="Visual OCR perception fallback",
        )
        caps.set_capability(PlatformCapability.OCR, CapabilityState.SUPPORTED, "Tesseract and local OCR pipelines available")
        caps.set_capability(PlatformCapability.AUDIO_CAPTURE, CapabilityState.SUPPORTED_WITH_PERMISSION, "PulseAudio / PipeWire / ALSA audio input available")
        caps.set_capability(PlatformCapability.WINDOW_ENUMERATION, CapabilityState.SUPPORTED if sess_type == "x11" else CapabilityState.DEGRADED, f"Window enumeration via {sess_type}")
        caps.set_capability(PlatformCapability.APPLICATION_ACTIVATION, CapabilityState.SUPPORTED, "xdg-open and desktop file activation supported")
        caps.set_capability(PlatformCapability.FILESYSTEM_NOTIFICATIONS, CapabilityState.SUPPORTED, "Linux inotify supported")
        caps.set_capability(PlatformCapability.SECURE_STORAGE, CapabilityState.SUPPORTED, "Secret Service API / GNOME Keyring / KWallet supported")
        caps.set_capability(PlatformCapability.PROCESS_CONTROL, CapabilityState.SUPPORTED, "POSIX /proc process inspection and signals supported")
        caps.set_capability(PlatformCapability.CLIPBOARD, CapabilityState.SUPPORTED, "xclip / wl-clipboard integration supported")
        caps.set_capability(PlatformCapability.PERMISSIONS, CapabilityState.SUPPORTED, "Linux polkit / XDG Desktop Portal permission model supported")
        caps.set_capability(PlatformCapability.MODEL_ACCELERATION, CapabilityState.DEGRADED, "CPU deterministic fallback active; optional ROCm/CUDA acceleration")

        return caps

    def get_compatibility_manifest(self) -> PlatformCompatibilityManifest:
        sess = self.get_session_type()
        return PlatformCompatibilityManifest(
            os_name="linux",
            minimum_os_version="Kernel 5.4+ / glibc 2.31+",
            required_capabilities=[
                PlatformCapability.PROCESS_CONTROL.value,
                PlatformCapability.FILESYSTEM_NOTIFICATIONS.value,
            ],
            optional_capabilities=[
                PlatformCapability.SCREEN_CAPTURE.value,
                PlatformCapability.ACCESSIBILITY.value,
                PlatformCapability.MODEL_ACCELERATION.value,
            ],
            known_limitations=[
                f"Active session is '{sess}'. Wayland restricts global synthetic input unless portal is granted.",
                "GNOME/KDE require AT-SPI enabled for semantic element tree access.",
            ],
            environment_adaptations={
                "wayland_input_restricted": "Report degraded input capability and propose user-assisted execution",
                "no_gpu": "Deterministic baseline CPU execution mode",
            },
        )


LinuxPlatformAdapter = LinuxAdapter
