"""Recording session model, state machine, and manifest specification."""

import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from teach_a_skill.core.errors import TeachSkillError


class SessionStateError(TeachSkillError):
    """Raised when an invalid session state transition is attempted."""


class SessionState(str, Enum):
    """Lifecycle states of a demonstration recording session."""

    CREATED = "CREATED"
    RECORDING = "RECORDING"
    PAUSED = "PAUSED"
    STOPPING = "STOPPING"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"
    FAILED = "FAILED"

    def __str__(self) -> str:
        return self.value


VALID_TRANSITIONS: dict[SessionState, set[SessionState]] = {
    SessionState.CREATED: {SessionState.RECORDING, SessionState.ABORTED},
    SessionState.RECORDING: {
        SessionState.PAUSED,
        SessionState.STOPPING,
        SessionState.ABORTED,
        SessionState.FAILED,
    },
    SessionState.PAUSED: {
        SessionState.RECORDING,
        SessionState.STOPPING,
        SessionState.ABORTED,
        SessionState.FAILED,
    },
    SessionState.STOPPING: {
        SessionState.COMPLETED,
        SessionState.FAILED,
        SessionState.ABORTED,
    },
    SessionState.COMPLETED: set(),  # Terminal
    SessionState.ABORTED: set(),  # Terminal
    SessionState.FAILED: set(),  # Terminal
}


@dataclass
class SessionSummary:
    """Deterministic, non-AI summary of a recorded demonstration session."""

    session_id: str
    status: str
    duration_sec: float
    total_events: int
    mouse_events: int
    keyboard_events: int
    window_events: int
    screenshots_captured: int
    displays_count: int
    distinct_applications: list[str]
    capture_profile: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def format_text(self) -> str:
        apps_str = (
            ", ".join(self.distinct_applications) if self.distinct_applications else "None detected"
        )
        return (
            f"Demonstration Session Summary:\n"
            f"  Session ID:      {self.session_id}\n"
            f"  Status:          {self.status}\n"
            f"  Duration:        {self.duration_sec:.2f} sec\n"
            f"  Total Events:    {self.total_events}\n"
            f"  Mouse Events:    {self.mouse_events}\n"
            f"  Keyboard Events: {self.keyboard_events}\n"
            f"  Window Events:   {self.window_events}\n"
            f"  Screenshots:     {self.screenshots_captured}\n"
            f"  Displays:        {self.displays_count}\n"
            f"  Applications:    {apps_str}\n"
            f"  Capture Profile: {self.capture_profile}"
        )


@dataclass
class SessionManifest:
    """Immutable on-disk descriptor manifest for a recording session."""

    session_id: str
    schema_version: int = 1
    recorder_version: str = "0.2.0"
    privacy_policy_version: int = 1
    status: SessionState = SessionState.CREATED
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    duration_sec: float = 0.0
    platform: str = "unknown"
    architecture: str = "unknown"
    capture_profile: str = "BALANCED"
    display_configuration: list[dict[str, Any]] = field(default_factory=list)
    hardware_profile: dict[str, Any] = field(default_factory=dict)
    event_count: int = 0
    event_counts_by_type: dict[str, int] = field(default_factory=dict)
    screen_capture_statistics: dict[str, Any] = field(default_factory=dict)
    distinct_applications: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = str(self.status)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionManifest":
        status_val = data.get("status", "CREATED")
        try:
            status = SessionState(status_val)
        except ValueError:
            status = SessionState.FAILED

        return cls(
            session_id=data["session_id"],
            schema_version=data.get("schema_version", 1),
            recorder_version=data.get("recorder_version", "0.2.0"),
            privacy_policy_version=data.get("privacy_policy_version", 1),
            status=status,
            created_at=data.get("created_at", ""),
            started_at=data.get("started_at"),
            ended_at=data.get("ended_at"),
            duration_sec=float(data.get("duration_sec", 0.0)),
            platform=data.get("platform", "unknown"),
            architecture=data.get("architecture", "unknown"),
            capture_profile=data.get("capture_profile", "BALANCED"),
            display_configuration=data.get("display_configuration", []),
            hardware_profile=data.get("hardware_profile", {}),
            event_count=int(data.get("event_count", 0)),
            event_counts_by_type=data.get("event_counts_by_type", {}),
            screen_capture_statistics=data.get("screen_capture_statistics", {}),
            distinct_applications=data.get("distinct_applications", []),
        )


class RecordingSession:
    """Manages the session state transitions and statistical aggregation."""

    def __init__(
        self,
        session_id: str,
        platform_name: str,
        architecture: str,
        hardware_profile: Optional[dict[str, Any]] = None,
        capture_profile: str = "BALANCED",
        display_config: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        self.manifest = SessionManifest(
            session_id=session_id,
            platform=platform_name,
            architecture=architecture,
            hardware_profile=hardware_profile or {},
            capture_profile=capture_profile,
            display_configuration=display_config or [],
        )
        self._start_monotonic: Optional[float] = None
        self._pause_monotonic: Optional[float] = None
        self._total_paused_duration: float = 0.0

    @property
    def session_id(self) -> str:
        return self.manifest.session_id

    @property
    def state(self) -> SessionState:
        return self.manifest.status

    def transition_to(self, new_state: SessionState) -> None:
        """Execute a state machine transition, rejecting invalid transitions."""
        current = self.manifest.status
        allowed = VALID_TRANSITIONS.get(current, set())
        if new_state not in allowed:
            raise SessionStateError(
                f"Invalid state transition: cannot transition from {current} to {new_state}. "
                f"Allowed target states: {[s.value for s in allowed]}"
            )

        now_utc = datetime.now(timezone.utc).isoformat()
        now_mono = time.monotonic()

        if new_state == SessionState.RECORDING:
            if current == SessionState.CREATED:
                self.manifest.started_at = now_utc
                self._start_monotonic = now_mono
            elif current == SessionState.PAUSED and self._pause_monotonic is not None:
                self._total_paused_duration += now_mono - self._pause_monotonic
                self._pause_monotonic = None

        elif new_state == SessionState.PAUSED:
            self._pause_monotonic = now_mono

        elif new_state in (SessionState.COMPLETED, SessionState.ABORTED, SessionState.FAILED):
            self.manifest.ended_at = now_utc
            if self._start_monotonic is not None:
                total_elapsed = now_mono - self._start_monotonic
                self.manifest.duration_sec = max(0.0, total_elapsed - self._total_paused_duration)

        self.manifest.status = new_state

    def record_event_metric(self, event_type: str, app_name: Optional[str] = None) -> None:
        """Increment event counter statistics."""
        self.manifest.event_count += 1
        counts = self.manifest.event_counts_by_type
        counts[event_type] = counts.get(event_type, 0) + 1

        if app_name and app_name not in self.manifest.distinct_applications:
            self.manifest.distinct_applications.append(app_name)

    def record_frame_metric(self, frame_id: str, trigger_reason: str) -> None:
        """Increment screenshot statistics."""
        stats = self.manifest.screen_capture_statistics
        stats["total_frames"] = stats.get("total_frames", 0) + 1
        triggers = stats.setdefault("triggers", {})
        triggers[trigger_reason] = triggers.get(trigger_reason, 0) + 1

    def get_summary(self) -> SessionSummary:
        """Produce a non-AI deterministic session summary."""
        counts = self.manifest.event_counts_by_type
        mouse_count = sum(v for k, v in counts.items() if k.startswith("MOUSE_"))
        kb_count = sum(v for k, v in counts.items() if k.startswith("KEY_") or k == "TEXT_INPUT")
        win_count = sum(v for k, v in counts.items() if k.startswith("WINDOW_"))
        screen_count = self.manifest.screen_capture_statistics.get("total_frames", 0)

        return SessionSummary(
            session_id=self.manifest.session_id,
            status=str(self.manifest.status),
            duration_sec=round(self.manifest.duration_sec, 2),
            total_events=self.manifest.event_count,
            mouse_events=mouse_count,
            keyboard_events=kb_count,
            window_events=win_count,
            screenshots_captured=screen_count,
            displays_count=len(self.manifest.display_configuration),
            distinct_applications=list(self.manifest.distinct_applications),
            capture_profile=self.manifest.capture_profile,
        )
