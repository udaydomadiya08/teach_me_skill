"""Mouse interaction model, actions, and movement coalescing engine.

Ensures high-frequency mouse movements do not flood I/O buffers while strictly
preserving drag trajectories, clicks, inflection points, and start/end points.
"""

import math
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class MouseButton(str, Enum):
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    MIDDLE = "MIDDLE"
    OTHER = "OTHER"

    def __str__(self) -> str:
        return self.value


class MouseAction(str, Enum):
    MOVE = "MOVE"
    DOWN = "DOWN"
    UP = "UP"
    CLICK = "CLICK"
    DOUBLE_CLICK = "DOUBLE_CLICK"
    SCROLL = "SCROLL"
    DRAG = "DRAG"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class MouseEventPayload:
    """Normalized payload for mouse events."""

    x: float
    y: float
    action: MouseAction
    button: Optional[MouseButton] = None
    dx: float = 0.0
    dy: float = 0.0
    display_id: int = 0
    scale_factor: float = 1.0
    modifiers: list[str] = field(default_factory=list)
    is_drag: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["action"] = str(self.action)
        if self.button:
            data["button"] = str(self.button)
        return data


class MovementCoalescer:
    """Buffers and filters high-frequency mouse movement to preserve system performance.

    Guarantees:
    - Never drops button presses or releases.
    - Preserves drag trajectories (start, key inflection points, and end).
    - Filters stationary micro-jitter (sub-threshold movements).
    - Preserves trajectory directional changes.
    """

    def __init__(
        self,
        min_distance_px: float = 6.0,
        min_interval_sec: float = 0.025,  # ~40 Hz max sample rate for raw moves
        direction_threshold_rad: float = 0.35,  # ~20 degrees
    ) -> None:
        self.min_distance_px = min_distance_px
        self.min_interval_sec = min_interval_sec
        self.direction_threshold_rad = direction_threshold_rad

        self._last_emitted_x: Optional[float] = None
        self._last_emitted_y: Optional[float] = None
        self._last_emitted_time: float = 0.0
        self._last_angle: Optional[float] = None

        self._is_button_down: bool = False
        self._drag_start_point: Optional[tuple[float, float]] = None

    def notify_button_state(
        self,
        button: MouseButton,
        is_down: bool,
        x: float,
        y: float,
        now_mono: Optional[float] = None,
    ) -> None:
        """Inform coalescer of button state to activate drag trajectory tracking."""
        self._is_button_down = is_down
        if is_down:
            self._drag_start_point = (x, y)
        else:
            self._drag_start_point = None
        # Always reset last emitted so subsequent move starts fresh
        self._last_emitted_x = x
        self._last_emitted_y = y
        self._last_emitted_time = time.monotonic() if now_mono is None else now_mono
        self._last_angle = None

    def should_emit_movement(self, x: float, y: float, now_mono: Optional[float] = None) -> bool:
        """Determine whether the current mouse position represents a meaningful movement sample."""
        now = time.monotonic() if now_mono is None else now_mono

        # First movement ever observed
        if self._last_emitted_x is None or self._last_emitted_y is None:
            self._emit(x, y, now)
            return True

        dx = x - self._last_emitted_x
        dy = y - self._last_emitted_y
        dist = math.hypot(dx, dy)
        dt = now - self._last_emitted_time

        # If button is down (active drag), be more sensitive to capture smooth trajectory
        effective_min_dist = (
            self.min_distance_px * 0.5 if self._is_button_down else self.min_distance_px
        )
        effective_min_interval = (
            self.min_interval_sec * 0.6 if self._is_button_down else self.min_interval_sec
        )

        # Condition 1: Distance too small (jitter)
        if dist < effective_min_dist:
            return False

        # Condition 2: Interval too fast without directional change
        if dt < effective_min_interval:
            # Check for significant directional change
            current_angle = math.atan2(dy, dx)
            if self._last_angle is not None:
                angle_diff = abs(current_angle - self._last_angle)
                if angle_diff > math.pi:
                    angle_diff = 2 * math.pi - angle_diff
                if angle_diff > self.direction_threshold_rad:
                    # Significant turn in movement trajectory! Emit to preserve curve
                    self._emit(x, y, now, current_angle)
                    return True
            return False

        # Condition 3: Time elapsed and distance threshold exceeded
        current_angle = math.atan2(dy, dx)
        self._emit(x, y, now, current_angle)
        return True

    def _emit(self, x: float, y: float, timestamp: float, angle: Optional[float] = None) -> None:
        self._last_emitted_x = x
        self._last_emitted_y = y
        self._last_emitted_time = timestamp
        self._last_angle = angle

    def flush_final_point(self, x: float, y: float) -> bool:
        """Emit final position before a button up or gesture end if not already at last emitted."""
        if self._last_emitted_x != x or self._last_emitted_y != y:
            self._emit(x, y, time.monotonic())
            return True
        return False
