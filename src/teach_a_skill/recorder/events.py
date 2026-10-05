"""Structured event representation and taxonomy for demonstration recording.

Preserves immutable raw event evidence with dual timestamps (wall-clock and monotonic),
sequence numbers, and strict priority classifications.
"""

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class EventType(str, Enum):
    """Canonical event types for physical interactions and system milestones."""

    # Session milestones
    SESSION_STARTED = "SESSION_STARTED"
    SESSION_PAUSED = "SESSION_PAUSED"
    SESSION_RESUMED = "SESSION_RESUMED"
    SESSION_STOPPED = "SESSION_STOPPED"
    SESSION_ABORTED = "SESSION_ABORTED"

    # Mouse events
    MOUSE_MOVE = "MOUSE_MOVE"
    MOUSE_DOWN = "MOUSE_DOWN"
    MOUSE_UP = "MOUSE_UP"
    MOUSE_CLICK = "MOUSE_CLICK"
    MOUSE_DOUBLE_CLICK = "MOUSE_DOUBLE_CLICK"
    MOUSE_SCROLL = "MOUSE_SCROLL"
    MOUSE_DRAG = "MOUSE_DRAG"

    # Keyboard events
    KEY_DOWN = "KEY_DOWN"
    KEY_UP = "KEY_UP"
    TEXT_INPUT = "TEXT_INPUT"

    # Window & Application context events
    WINDOW_FOCUS_CHANGED = "WINDOW_FOCUS_CHANGED"
    WINDOW_CREATED = "WINDOW_CREATED"
    WINDOW_CLOSED = "WINDOW_CLOSED"
    WINDOW_MOVED = "WINDOW_MOVED"
    WINDOW_RESIZED = "WINDOW_RESIZED"

    # Display configuration
    DISPLAY_CONFIGURATION_CHANGED = "DISPLAY_CONFIGURATION_CHANGED"

    # Visual perception checkpoints
    SCREENSHOT_CAPTURED = "SCREENSHOT_CAPTURED"
    SCREEN_STATE_CHANGED = "SCREEN_STATE_CHANGED"

    # Diagnostics & Observability
    RECORDER_WARNING = "RECORDER_WARNING"
    RECORDER_ERROR = "RECORDER_ERROR"

    def __str__(self) -> str:
        return self.value


class EventPriority(str, Enum):
    """Data priority governing backpressure drop policies."""

    CRITICAL = "CRITICAL"  # User clicks, keystrokes, session states. NEVER drop.
    HIGH = "HIGH"  # Window focus, display changes. Drop only in severe crisis.
    MEDIUM = "MEDIUM"  # Dense mouse movement samples. Drop redundant samples.
    LOW = "LOW"  # Periodic screenshots/checkpoints. Drop first when congested.

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Event:
    """Strongly structured raw demonstration event."""

    event_id: str
    session_id: str
    sequence_number: int
    timestamp: str  # ISO 8601 UTC
    monotonic_timestamp: float  # High-resolution monotonic clock (seconds)
    event_type: EventType
    priority: EventPriority
    source: str  # "mouse", "keyboard", "window", "screen", "system", "synthetic"
    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        session_id: str,
        sequence_number: int,
        event_type: EventType,
        source: str,
        payload: Optional[dict[str, Any]] = None,
        priority: Optional[EventPriority] = None,
        event_id: Optional[str] = None,
        monotonic_ts: Optional[float] = None,
    ) -> "Event":
        """Factory creating a properly timestamped and sequenced event."""
        now_utc = datetime.now(timezone.utc).isoformat()
        mono = time.monotonic() if monotonic_ts is None else monotonic_ts
        eid = event_id or f"evt_{uuid.uuid4().hex[:12]}"

        # Infer default priority if not provided
        if priority is None:
            if event_type in (
                EventType.SESSION_STARTED,
                EventType.SESSION_PAUSED,
                EventType.SESSION_RESUMED,
                EventType.SESSION_STOPPED,
                EventType.SESSION_ABORTED,
                EventType.MOUSE_DOWN,
                EventType.MOUSE_UP,
                EventType.MOUSE_CLICK,
                EventType.MOUSE_DOUBLE_CLICK,
                EventType.KEY_DOWN,
                EventType.KEY_UP,
                EventType.TEXT_INPUT,
            ):
                priority = EventPriority.CRITICAL
            elif event_type in (
                EventType.WINDOW_FOCUS_CHANGED,
                EventType.WINDOW_CREATED,
                EventType.WINDOW_CLOSED,
                EventType.WINDOW_MOVED,
                EventType.WINDOW_RESIZED,
                EventType.DISPLAY_CONFIGURATION_CHANGED,
            ):
                priority = EventPriority.HIGH
            elif event_type in (EventType.MOUSE_MOVE, EventType.MOUSE_DRAG, EventType.MOUSE_SCROLL):
                priority = EventPriority.MEDIUM
            else:
                priority = EventPriority.LOW

        return cls(
            event_id=eid,
            session_id=session_id,
            sequence_number=sequence_number,
            timestamp=now_utc,
            monotonic_timestamp=mono,
            event_type=event_type,
            priority=priority,
            source=source,
            payload=payload or {},
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize event to a JSON-compatible dictionary."""
        data = asdict(self)
        data["event_type"] = str(self.event_type)
        data["priority"] = str(self.priority)
        return data

    def to_json(self) -> str:
        """Serialize event to compact JSON string."""
        return json.dumps(self.to_dict(), separators=(",", ":"))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Event":
        """Deserialize an event from dictionary representation."""
        return cls(
            event_id=data["event_id"],
            session_id=data["session_id"],
            sequence_number=data["sequence_number"],
            timestamp=data["timestamp"],
            monotonic_timestamp=float(data["monotonic_timestamp"]),
            event_type=EventType(data["event_type"]),
            priority=EventPriority(data["priority"]),
            source=data["source"],
            payload=data.get("payload", {}),
        )
