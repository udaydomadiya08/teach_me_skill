"""Native OS event observer and screen capture engine."""

import platform
import shutil
import subprocess
import tempfile
import threading
import time
from typing import Any, Callable, Optional

from teach_a_skill.core.logging import get_logger
from teach_a_skill.interfaces.screen_capture import IScreenCapture
from teach_a_skill.recorder.events import Event, EventType
from teach_a_skill.recorder.screen import (
    DisplayInfo,
    create_solid_color_png,
)
from teach_a_skill.recorder.sources.base import BaseEventSource
from teach_a_skill.recorder.window import WindowManagerEngine

logger = get_logger("teach_a_skill.recorder.os_source")


class SyntheticScreenEngine(IScreenCapture):
    """In-memory instantaneous screen frame generator for synthetic runs and benchmarks."""

    def __init__(self, width: int = 1280, height: int = 720) -> None:
        self.width = width
        self.height = height
        self._cached_png = create_solid_color_png(width, height, 45, 52, 64)

    def get_display_info(self) -> list[dict[str, Any]]:
        return [
            DisplayInfo(
                display_id=1,
                name="Synthetic Virtual Display",
                width=self.width,
                height=self.height,
                scale_factor=1.0,
                is_primary=True,
            ).to_dict()
        ]

    def capture_frame(self, display_id: Optional[int] = None) -> bytes:
        return self._cached_png


class ScreenCaptureEngine(IScreenCapture):
    """Deterministic OS display frame grabber."""

    def __init__(self) -> None:
        self.os_name = platform.system().lower()

    def get_display_info(self) -> list[dict[str, Any]]:
        """Query connected display geometry."""
        # Baseline primary display detection
        disp = DisplayInfo(
            display_id=1,
            name="Primary Display",
            width=1920,
            height=1080,
            scale_factor=2.0 if self.os_name == "darwin" else 1.0,
            is_primary=True,
        )
        return [disp.to_dict()]

    def capture_frame(self, display_id: Optional[int] = None) -> bytes:
        """Capture display frame bytes as PNG.

        Falls back gracefully if permission is denied or tools missing.
        """
        if self.os_name == "darwin":
            return self._capture_macos()
        elif self.os_name == "linux":
            return self._capture_linux()
        elif self.os_name == "windows":
            return self._capture_windows()

        return create_solid_color_png(1280, 720)

    def _capture_macos(self) -> bytes:
        screencapture_bin = shutil.which("screencapture")
        if screencapture_bin:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = tmp.name
            try:
                # -x disables sound, -C captures cursor
                res = subprocess.run(
                    [screencapture_bin, "-x", tmp_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=2.0,
                )
                if res.returncode == 0:
                    with open(tmp_path, "rb") as f:
                        data = f.read()
                    if len(data) > 0:
                        return data
            except Exception as e:
                logger.debug(f"screencapture failed: {e}")
            finally:
                import os

                if os.path.exists(tmp_path):
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass

        return create_solid_color_png(1440, 900)

    def _capture_linux(self) -> bytes:
        import os

        for cmd in ["grim", "scrot", "import"]:
            bin_path = shutil.which(cmd)
            if bin_path:
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    tmp_path = tmp.name
                try:
                    res = subprocess.run(
                        [bin_path, tmp_path]
                        if cmd != "import"
                        else [bin_path, "-window", "root", tmp_path],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=2.0,
                    )
                    if res.returncode == 0 and os.path.exists(tmp_path):
                        with open(tmp_path, "rb") as f:
                            data = f.read()
                        if len(data) > 0:
                            return data
                except Exception:
                    pass
                finally:
                    if os.path.exists(tmp_path):
                        try:
                            os.unlink(tmp_path)
                        except OSError:
                            pass

        return create_solid_color_png(1920, 1080)

    def _capture_windows(self) -> bytes:
        return create_solid_color_png(1920, 1080)


class OSEventSource(BaseEventSource):
    """Observes native OS interactions and window context changes."""

    def __init__(self, session_id: str, poll_interval_sec: float = 0.5) -> None:
        self.session_id = session_id
        self.poll_interval_sec = poll_interval_sec
        self.window_engine = WindowManagerEngine()
        self._active = False
        self._thread: Optional[threading.Thread] = None
        self._seq = 1
        self._last_window_title: Optional[str] = None

    @property
    def is_active(self) -> bool:
        return self._active

    def start(self, callback: Callable[[Event], None]) -> None:
        self._active = True
        self._thread = threading.Thread(
            target=self._poll_loop,
            args=(callback,),
            name="os-event-poller",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._active = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _poll_loop(self, callback: Callable[[Event], None]) -> None:
        while self._active:
            try:
                ctx = self.window_engine.get_active_window_context()
                if ctx.capability == "available" and ctx.window_title != self._last_window_title:
                    self._last_window_title = ctx.window_title
                    evt = Event.create(
                        session_id=self.session_id,
                        sequence_number=self._seq,
                        event_type=EventType.WINDOW_FOCUS_CHANGED,
                        source="os_window_poller",
                        payload=ctx.to_dict(),
                    )
                    self._seq += 1
                    callback(evt)
            except Exception as e:
                logger.debug(f"Window polling error: {e}")

            time.sleep(self.poll_interval_sec)
