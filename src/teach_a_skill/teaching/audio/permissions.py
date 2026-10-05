"""Platform microphone permission queries and diagnostic reporting."""

import platform
import shutil
import subprocess
from enum import Enum
from typing import Any

from teach_a_skill.core.logging import get_logger

logger = get_logger("teach_a_skill.teaching.audio.permissions")


class AudioPermissionStatus(str, Enum):
    """Status of microphone access on host operating system."""

    GRANTED = "GRANTED"
    DENIED = "DENIED"
    NOT_REQUIRED = "NOT_REQUIRED"
    UNKNOWN = "UNKNOWN"
    UNSUPPORTED = "UNSUPPORTED"

    def __str__(self) -> str:
        return self.value


class AudioPermissionManager:
    """Detects and reports microphone recording permissions."""

    def __init__(self) -> None:
        self.os_type = platform.system().lower()

    def check_permission(self) -> AudioPermissionStatus:
        """Alias for check_microphone_permission."""
        return self.check_microphone_permission()

    def check_microphone_permission(self) -> AudioPermissionStatus:
        """Query platform OS for microphone capture authorization."""
        if self.os_type == "darwin":
            # On macOS, check if ffmpeg or python has access
            # We can check TCC database status or run a dry run
            if shutil.which("ffmpeg") is None and shutil.which("sox") is None:
                return AudioPermissionStatus.UNKNOWN

            # A lightweight probe with ffmpeg to see if permission error is raised
            try:
                # 0.1 second probe to test if audio device opens
                cmd = [
                    shutil.which("ffmpeg") or "ffmpeg",
                    "-f",
                    "avfoundation",
                    "-i",
                    ":0",
                    "-t",
                    "0.05",
                    "-f",
                    "null",
                    "-",
                ]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=1.5)
                if "Permission denied" in res.stderr or "not permitted" in res.stderr:
                    return AudioPermissionStatus.DENIED
                return AudioPermissionStatus.GRANTED
            except subprocess.TimeoutExpired:
                return AudioPermissionStatus.GRANTED
            except Exception:
                return AudioPermissionStatus.UNKNOWN

        elif self.os_type == "linux":
            # Linux typically requires read access to /dev/snd/* or PulseAudio/PipeWire socket
            if (
                shutil.which("arecord") is not None
                or shutil.which("parecord") is not None
                or shutil.which("ffmpeg") is not None
            ):
                return AudioPermissionStatus.NOT_REQUIRED
            return AudioPermissionStatus.UNSUPPORTED

        elif self.os_type == "windows":
            if shutil.which("ffmpeg") is not None:
                return AudioPermissionStatus.NOT_REQUIRED
            return AudioPermissionStatus.UNKNOWN

        return AudioPermissionStatus.UNSUPPORTED

    def get_permission_report(self) -> dict[str, Any]:
        """Generate human-readable diagnostic report for microphone permissions."""
        status = self.check_microphone_permission()
        diagnostic = ""

        if status == AudioPermissionStatus.GRANTED:
            diagnostic = "Microphone capture authorized and available."
        elif status == AudioPermissionStatus.DENIED:
            if self.os_type == "darwin":
                diagnostic = (
                    "Microphone access DENIED. Please enable Microphone permissions in "
                    "System Settings -> Privacy & Security -> Microphone for Terminal / Python."
                )
            else:
                diagnostic = "Microphone access denied by host OS security settings."
        elif status == AudioPermissionStatus.UNSUPPORTED:
            diagnostic = "Audio capture subsystem not detected on this host. Text teaching remains available."
        else:
            diagnostic = "Microphone authorization status unknown or external tool not found."

        return {
            "status": status.value,
            "os": self.os_type,
            "diagnostic": diagnostic,
        }
