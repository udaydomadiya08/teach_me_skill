"""Cross-platform permissions, capability detection, and user diagnostics."""

import platform
import shutil
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class PermissionType(str, Enum):
    SCREEN_CAPTURE = "SCREEN_CAPTURE"
    INPUT_MONITORING = "INPUT_MONITORING"
    ACCESSIBILITY = "ACCESSIBILITY"
    WINDOW_METADATA = "WINDOW_METADATA"

    def __str__(self) -> str:
        return self.value


class PermissionStatus(str, Enum):
    GRANTED = "GRANTED"
    DENIED = "DENIED"
    NOT_REQUIRED = "NOT_REQUIRED"
    UNKNOWN = "UNKNOWN"
    UNSUPPORTED = "UNSUPPORTED"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class PermissionReport:
    permission_type: PermissionType
    status: PermissionStatus
    description: str
    remediation_hint: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "permission_type": str(self.permission_type),
            "status": str(self.status),
            "description": self.description,
            "remediation_hint": self.remediation_hint,
        }


class PlatformPermissionManager:
    """Introspects OS permission boundaries without prompting unnecessarily."""

    def __init__(self) -> None:
        self.os_name = platform.system().lower()

    def check_permissions(self) -> list[PermissionReport]:
        """Inspect all permissions required for demonstration recording."""
        if self.os_name == "darwin":
            return self._check_macos_permissions()
        elif self.os_name == "linux":
            return self._check_linux_permissions()
        elif self.os_name == "windows":
            return self._check_windows_permissions()

        return [
            PermissionReport(
                permission_type=PermissionType.SCREEN_CAPTURE,
                status=PermissionStatus.UNSUPPORTED,
                description=f"Unsupported OS: {self.os_name}",
            )
        ]

    def _check_macos_permissions(self) -> list[PermissionReport]:
        reports: list[PermissionReport] = []

        # 1. Screen capture capability
        has_screencapture = shutil.which("screencapture") is not None
        reports.append(
            PermissionReport(
                permission_type=PermissionType.SCREEN_CAPTURE,
                status=PermissionStatus.GRANTED if has_screencapture else PermissionStatus.DENIED,
                description="macOS Screen Recording permission allows capturing display frames.",
                remediation_hint="System Settings > Privacy & Security > Screen Recording",
            )
        )

        # 2. Input monitoring
        reports.append(
            PermissionReport(
                permission_type=PermissionType.INPUT_MONITORING,
                status=PermissionStatus.UNKNOWN,
                description="macOS Input Monitoring permission allows observing mouse and keyboard events.",
                remediation_hint="System Settings > Privacy & Security > Input Monitoring",
            )
        )

        # 3. Accessibility
        reports.append(
            PermissionReport(
                permission_type=PermissionType.ACCESSIBILITY,
                status=PermissionStatus.UNKNOWN,
                description="macOS Accessibility permission allows observing window hierarchy and event taps.",
                remediation_hint="System Settings > Privacy & Security > Accessibility",
            )
        )

        # 4. Window metadata
        reports.append(
            PermissionReport(
                permission_type=PermissionType.WINDOW_METADATA,
                status=PermissionStatus.GRANTED,
                description="Window metadata accessible via AppleScript System Events.",
            )
        )

        return reports

    def _check_linux_permissions(self) -> list[PermissionReport]:
        # Linux typically does not require app-specific permission dialogs on X11,
        # but Wayland requires PipeWire portal.
        is_wayland = (
            "wayland" in platform.freedesktop_os_release().get("XDG_SESSION_TYPE", "").lower()
        )
        status = PermissionStatus.GRANTED if not is_wayland else PermissionStatus.UNKNOWN

        return [
            PermissionReport(
                permission_type=PermissionType.SCREEN_CAPTURE,
                status=status,
                description="Screen capture via X11 / PipeWire Portal.",
                remediation_hint="Ensure xdg-desktop-portal is installed on Wayland.",
            ),
            PermissionReport(
                permission_type=PermissionType.INPUT_MONITORING,
                status=PermissionStatus.GRANTED,
                description="Input capture via X11 or evdev/uinput.",
            ),
            PermissionReport(
                permission_type=PermissionType.WINDOW_METADATA,
                status=PermissionStatus.GRANTED,
                description="Window metadata via xdotool/AT-SPI.",
            ),
        ]

    def _check_windows_permissions(self) -> list[PermissionReport]:
        return [
            PermissionReport(
                permission_type=PermissionType.SCREEN_CAPTURE,
                status=PermissionStatus.GRANTED,
                description="Screen capture via Desktop Duplication / GDI.",
            ),
            PermissionReport(
                permission_type=PermissionType.INPUT_MONITORING,
                status=PermissionStatus.GRANTED,
                description="Input capture via Windows LowLevel Hooks.",
            ),
            PermissionReport(
                permission_type=PermissionType.WINDOW_METADATA,
                status=PermissionStatus.GRANTED,
                description="Window metadata via User32 Win32 API.",
            ),
        ]
