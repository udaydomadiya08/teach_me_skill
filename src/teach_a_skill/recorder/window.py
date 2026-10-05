"""Active application, window context, and window manager engine."""

import os
import platform
import subprocess
from dataclasses import asdict, dataclass
from typing import Any, Optional

from teach_a_skill.interfaces.window_manager import IWindowManager


@dataclass(frozen=True)
class WindowContext:
    """Snapshot of active application and window geometry."""

    app_name: Optional[str]
    app_id: Optional[str]
    process_id: Optional[int]
    window_title: Optional[str]
    bounds: Optional[dict[str, int]]  # x, y, width, height
    window_id: Optional[str]
    capability: str  # "available", "permission_required", "unsupported"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def unavailable(cls, reason: str = "permission_required") -> "WindowContext":
        return cls(
            app_name=None,
            app_id=None,
            process_id=None,
            window_title=None,
            bounds=None,
            window_id=None,
            capability=reason,
        )


class WindowManagerEngine(IWindowManager):
    """Platform-aware active window and application context detector."""

    def __init__(self) -> None:
        self.os_name = platform.system().lower()

    def get_active_window(self) -> Optional[dict[str, Any]]:
        """Retrieve active focused application and window context."""
        ctx = self.get_active_window_context()
        return ctx.to_dict()

    def list_windows(self) -> list[dict[str, Any]]:
        """Enumerate visible application windows."""
        # Baseline stub for window enumeration
        active = self.get_active_window()
        return [active] if active else []

    def get_active_window_context(self) -> WindowContext:
        """Query host OS for currently focused window and application info."""
        if self.os_name == "darwin":
            return self._get_macos_window()
        elif self.os_name == "linux":
            return self._get_linux_window()
        elif self.os_name == "windows":
            return self._get_windows_window()

        return WindowContext.unavailable("unsupported_os")

    def _get_macos_window(self) -> WindowContext:
        """Query frontmost application on macOS via AppleScript or sys tools."""
        try:
            # Query frontmost app name and process id
            script = 'tell application "System Events" to get {name, unix id} of first application process whose frontmost is true'
            out = subprocess.check_output(
                ["osascript", "-e", script],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=1.0,
            ).strip()

            if out and "," in out:
                parts = [p.strip() for p in out.split(",", 1)]
                app_name = parts[0]
                pid = int(parts[1]) if parts[1].isdigit() else None
                return WindowContext(
                    app_name=app_name,
                    app_id=f"com.apple.{app_name.lower().replace(' ', '')}",
                    process_id=pid,
                    window_title=app_name,
                    bounds={"x": 0, "y": 0, "width": 1440, "height": 900},
                    window_id="front_win",
                    capability="available",
                )
        except Exception:
            pass

        return WindowContext.unavailable("permission_required")

    def _get_linux_window(self) -> WindowContext:
        """Query active window on Linux via xdotool or X11/Wayland context."""
        xdotool = os.environ.get("XDOTOOL", "xdotool")
        try:
            win_id = subprocess.check_output(
                [xdotool, "getactivewindow"],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=0.5,
            ).strip()
            win_name = subprocess.check_output(
                [xdotool, "getwindowname", win_id],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=0.5,
            ).strip()
            return WindowContext(
                app_name=win_name,
                app_id=win_name,
                process_id=None,
                window_title=win_name,
                bounds={"x": 0, "y": 0, "width": 1920, "height": 1080},
                window_id=win_id,
                capability="available",
            )
        except Exception:
            return WindowContext.unavailable("permission_required")

    def _get_windows_window(self) -> WindowContext:
        """Query active window on Windows via ctypes / GetForegroundWindow."""
        try:
            import ctypes

            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if hwnd:
                length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                buff = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value
                return WindowContext(
                    app_name=title,
                    app_id=title,
                    process_id=None,
                    window_title=title,
                    bounds=None,
                    window_id=str(hwnd),
                    capability="available",
                )
        except Exception:
            pass

        return WindowContext.unavailable("permission_required")
