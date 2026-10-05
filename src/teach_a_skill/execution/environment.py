"""Environment observation and adapter for runtime state discovery.

Provides an abstract interface for observing the live desktop environment,
with a concrete synthetic adapter for testing and a macOS adapter stub
for real accessibility integration.
"""

from __future__ import annotations

import logging
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, Optional

from teach_a_skill.execution.models import (
    EnvironmentElement,
    EnvironmentSnapshot,
)

logger = logging.getLogger(__name__)


class EnvironmentAdapter(ABC):
    """Abstract interface for observing the live desktop environment."""

    @abstractmethod
    def observe(self) -> EnvironmentSnapshot:
        """Capture a point-in-time snapshot of the environment."""
        ...

    @abstractmethod
    def get_active_application(self) -> Optional[str]:
        """Return the currently focused application name."""
        ...

    @abstractmethod
    def get_active_window_title(self) -> Optional[str]:
        """Return the currently focused window title."""
        ...

    @abstractmethod
    def get_running_applications(self) -> list[str]:
        """Return list of currently running application names."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the environment adapter can observe the system."""
        ...

    @abstractmethod
    def adapter_id(self) -> str:
        """Unique identifier for this adapter implementation."""
        ...


class SyntheticEnvironmentAdapter(EnvironmentAdapter):
    """In-memory environment adapter for deterministic testing.

    Allows pre-loading elements and application state for
    fully reproducible execution tests.
    """

    def __init__(
        self,
        elements: Optional[list[EnvironmentElement]] = None,
        active_app: str = "TextEdit",
        active_window: str = "Untitled",
        running_apps: Optional[list[str]] = None,
        screen_width: int = 1920,
        screen_height: int = 1080,
    ) -> None:
        self._elements = elements or []
        self._active_app = active_app
        self._active_window = active_window
        self._running_apps = running_apps or [active_app]
        self._screen_width = screen_width
        self._screen_height = screen_height

    def set_elements(self, elements: list[EnvironmentElement]) -> None:
        """Replace the current set of observed elements."""
        self._elements = list(elements)

    def add_element(self, element: EnvironmentElement) -> None:
        """Add a single element to the environment."""
        self._elements.append(element)

    def set_active_app(self, app_name: str, window_title: str = "Untitled") -> None:
        """Set the active application and window."""
        self._active_app = app_name
        self._active_window = window_title
        if app_name not in self._running_apps:
            self._running_apps.append(app_name)

    def observe(self) -> EnvironmentSnapshot:
        """Return a synthetic environment snapshot."""
        start = time.monotonic()
        snapshot = EnvironmentSnapshot(
            snapshot_id=f"snap_{uuid.uuid4().hex[:12]}",
            active_application=self._active_app,
            active_window_title=self._active_window,
            running_applications=list(self._running_apps),
            elements=list(self._elements),
            screen_width=self._screen_width,
            screen_height=self._screen_height,
            source="synthetic",
        )
        snapshot.observation_duration_ms = (time.monotonic() - start) * 1000
        return snapshot

    def get_active_application(self) -> Optional[str]:
        return self._active_app

    def get_active_window_title(self) -> Optional[str]:
        return self._active_window

    def get_running_applications(self) -> list[str]:
        return list(self._running_apps)

    def is_available(self) -> bool:
        return True

    def adapter_id(self) -> str:
        return "synthetic_environment"


class MacOSEnvironmentAdapter(EnvironmentAdapter):
    """macOS-specific environment adapter using Accessibility APIs.

    Falls back to screen-only observation when accessibility
    permissions are not granted.
    """

    def __init__(self) -> None:
        self._ax_available: Optional[bool] = None

    def _check_accessibility(self) -> bool:
        """Check if accessibility API access is available."""
        if self._ax_available is not None:
            return self._ax_available
        try:
            import subprocess

            # Check if process is trusted for accessibility
            result = subprocess.run(
                ["osascript", "-e", 'tell application "System Events" to return name of first process'],
                capture_output=True,
                text=True,
                timeout=5,
            )
            self._ax_available = result.returncode == 0
        except Exception:
            self._ax_available = False
        return self._ax_available

    def observe(self) -> EnvironmentSnapshot:
        """Observe the macOS desktop environment."""
        start = time.monotonic()
        elements: list[EnvironmentElement] = []
        active_app = self.get_active_application()
        active_window = self.get_active_window_title()
        running = self.get_running_applications()

        if self._check_accessibility() and active_app:
            try:
                import subprocess

                script = f'''
                tell application "System Events"
                    tell process "{active_app}"
                        set elemList to {{}}
                        if (count of windows) > 0 then
                            set win to first window
                            set winName to name of win
                            set end of elemList to "window::" & winName & "::" & winName
                            repeat with u in UI elements of win
                                try
                                    set uRole to role of u
                                    set uName to name of u
                                    if uName is not missing value and uName is not "" then
                                        set end of elemList to uRole & "::" & uName & "::" & winName
                                    end if
                                end try
                            end repeat
                        end if
                        return elemList
                    end tell
                end tell
                '''
                res = subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if res.returncode == 0 and res.stdout.strip():
                    raw_items = [x.strip() for x in res.stdout.strip().split(",") if x.strip()]
                    for idx, raw in enumerate(raw_items):
                        parts = raw.split("::")
                        role = parts[0] if len(parts) > 0 else "element"
                        label = parts[1] if len(parts) > 1 else ""
                        win = parts[2] if len(parts) > 2 else active_window or ""
                        if label:
                            elements.append(
                                EnvironmentElement(
                                    element_id=f"elem_{active_app}_{idx}",
                                    role=role,
                                    label=label,
                                    title=label,
                                    application=active_app,
                                    window_title=win,
                                )
                            )
            except Exception as e:
                logger.debug("Could not extract macOS UI elements: %s", e)

        snapshot = EnvironmentSnapshot(
            snapshot_id=f"snap_{uuid.uuid4().hex[:12]}",
            active_application=active_app,
            active_window_title=active_window,
            running_applications=running,
            elements=elements,
            source="macos_accessibility" if self._check_accessibility() else "macos_screen_only",
        )
        snapshot.observation_duration_ms = (time.monotonic() - start) * 1000
        return snapshot

    def get_active_application(self) -> Optional[str]:
        try:
            import subprocess

            result = subprocess.run(
                [
                    "osascript",
                    "-e",
                    'tell application "System Events" to return name of first application process whose frontmost is true',
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def get_active_window_title(self) -> Optional[str]:
        try:
            import subprocess

            result = subprocess.run(
                [
                    "osascript",
                    "-e",
                    'tell application "System Events" to return title of first window of first application process whose frontmost is true',
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def get_running_applications(self) -> list[str]:
        try:
            import subprocess

            result = subprocess.run(
                [
                    "osascript",
                    "-e",
                    'tell application "System Events" to return name of every application process whose visible is true',
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return [a.strip() for a in result.stdout.strip().split(",") if a.strip()]
        except Exception:
            pass
        return []

    def is_available(self) -> bool:
        return True

    def adapter_id(self) -> str:
        return "macos_environment"


def get_environment_adapter(synthetic: bool = False, **kwargs: Any) -> EnvironmentAdapter:
    """Factory function to return the appropriate environment adapter.

    Args:
        synthetic: If True, returns the synthetic test adapter.
        **kwargs: Extra keyword arguments passed to the adapter constructor.

    Returns:
        An EnvironmentAdapter instance.
    """
    if synthetic:
        return SyntheticEnvironmentAdapter(**kwargs)
    import platform

    if platform.system() == "Darwin":
        return MacOSEnvironmentAdapter()
    # Fallback to synthetic for unsupported platforms
    return SyntheticEnvironmentAdapter(**kwargs)


LocalEnvironmentAdapter = get_environment_adapter

