"""Canonical data models, event taxonomies, physical interactions, and demonstration containers."""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class ProvenanceView:
    """Attribute-access wrapper around a provenance dict."""

    def __init__(self, data: Optional[dict[str, Any]] = None) -> None:
        object.__setattr__(self, "_data", data if data is not None else {})

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(f"ProvenanceView has no attribute '{name}'")
        data = object.__getattribute__(self, "_data")
        try:
            return data[name]
        except (KeyError, TypeError):
            raise AttributeError(f"ProvenanceView has no attribute '{name}'")

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def __repr__(self) -> str:
        return f"ProvenanceView({self._data!r})"

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)

    def __deepcopy__(self, memo: Any) -> "ProvenanceView":
        import copy
        return ProvenanceView(copy.deepcopy(self._data, memo))


class EventCategory(str, Enum):
    """Broad category for canonical events."""

    POINTER = "POINTER"
    KEYBOARD = "KEYBOARD"
    WINDOW = "WINDOW"
    SCREEN = "SCREEN"
    SYSTEM = "SYSTEM"
    SESSION = "SESSION"

    def __str__(self) -> str:
        return self.value


class CanonicalEventType(str, Enum):
    """Normalized physical event types."""

    # Pointer interactions
    POINTER_MOVE = "POINTER_MOVE"
    POINTER_DOWN = "POINTER_DOWN"
    POINTER_UP = "POINTER_UP"
    CLICK = "CLICK"
    DOUBLE_CLICK = "DOUBLE_CLICK"
    SCROLL = "SCROLL"
    DRAG = "DRAG"

    # Keyboard interactions
    KEY_DOWN = "KEY_DOWN"
    KEY_UP = "KEY_UP"
    SHORTCUT = "SHORTCUT"
    TEXT_INPUT = "TEXT_INPUT"

    # Window & Application
    WINDOW_FOCUS = "WINDOW_FOCUS"
    WINDOW_CREATED = "WINDOW_CREATED"
    WINDOW_CLOSED = "WINDOW_CLOSED"
    WINDOW_MOVED = "WINDOW_MOVED"
    WINDOW_RESIZED = "WINDOW_RESIZED"

    # Visual perception checkpoints
    SCREEN_CAPTURE = "SCREEN_CAPTURE"
    SCREEN_STATE_CHANGED = "SCREEN_STATE_CHANGED"

    # Session lifecycle
    SESSION_START = "SESSION_START"
    SESSION_PAUSE = "SESSION_PAUSE"
    SESSION_RESUME = "SESSION_RESUME"
    SESSION_STOP = "SESSION_STOP"
    SESSION_ABORT = "SESSION_ABORT"

    # System
    DISPLAY_CHANGE = "DISPLAY_CHANGE"
    SYSTEM_WARNING = "SYSTEM_WARNING"
    SYSTEM_ERROR = "SYSTEM_ERROR"

    def __str__(self) -> str:
        return self.value


@dataclass
class CanonicalEvent:
    """Normalized, provenance-preserving demonstration event."""

    event_id: str
    source_event_id: str
    timestamp: str  # ISO UTC
    monotonic_timestamp: float  # Seconds
    relative_time_ms: float
    relative_time_ns: int
    category: EventCategory
    canonical_event_type: CanonicalEventType
    raw_event_type: str
    source: str
    sequence: int
    duration_ms: Optional[float] = None
    display_id: Optional[str] = None
    raw_x: Optional[float] = None
    raw_y: Optional[float] = None
    normalized_x: Optional[float] = None
    normalized_y: Optional[float] = None
    application: Optional[str] = None
    window_title: Optional[str] = None
    process_id: Optional[int] = None
    frame_reference: Optional[str] = None
    speech_reference: Optional[str] = None
    annotation_reference: Optional[str] = None
    payload: dict[str, Any] = field(default_factory=dict)
    provenance: Any = field(default_factory=dict)  # dict or ProvenanceView

    @property
    def event_category(self) -> EventCategory:
        return self.category

    @property
    def window(self) -> Optional[str]:
        """Alias for window_title."""
        return self.window_title

    def _provenance_dict(self) -> dict[str, Any]:
        if isinstance(self.provenance, ProvenanceView):
            return self.provenance.to_dict()
        return dict(self.provenance) if self.provenance else {}

    def to_dict(self) -> dict[str, Any]:
        if isinstance(self.provenance, ProvenanceView):
            prov = self.provenance.to_dict()
        elif isinstance(self.provenance, dict):
            prov = dict(self.provenance)
        else:
            prov = {}

        cat_val = self.category.value if hasattr(self.category, "value") else str(self.category)
        type_val = self.canonical_event_type.value if hasattr(self.canonical_event_type, "value") else str(self.canonical_event_type)

        return {
            "event_id": self.event_id,
            "source_event_id": self.source_event_id,
            "timestamp": self.timestamp,
            "monotonic_timestamp": self.monotonic_timestamp,
            "relative_time_ms": self.relative_time_ms,
            "relative_time_ns": self.relative_time_ns,
            "category": str(cat_val),
            "canonical_event_type": str(type_val),
            "raw_event_type": self.raw_event_type,
            "source": self.source,
            "sequence": self.sequence,
            "duration_ms": self.duration_ms,
            "display_id": self.display_id,
            "raw_x": self.raw_x,
            "raw_y": self.raw_y,
            "normalized_x": self.normalized_x,
            "normalized_y": self.normalized_y,
            "application": self.application,
            "window_title": self.window_title,
            "process_id": self.process_id,
            "frame_reference": self.frame_reference,
            "speech_reference": self.speech_reference,
            "annotation_reference": self.annotation_reference,
            "payload": dict(self.payload) if self.payload else {},
            "provenance": prov,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CanonicalEvent":
        data_copy = dict(data)
        data_copy["category"] = EventCategory(data_copy["category"])
        data_copy["canonical_event_type"] = CanonicalEventType(data_copy["canonical_event_type"])
        # Wrap provenance dict in ProvenanceView for attribute access
        if isinstance(data_copy.get("provenance"), dict):
            data_copy["provenance"] = ProvenanceView(data_copy["provenance"])
        return cls(**data_copy)


@dataclass
class PointerPoint:
    """Coordinate sample on a continuous pointer path."""

    x: float
    y: float
    relative_time_ms: float
    monotonic_ns: int


@dataclass
class PointerPath:
    """Continuous physical mouse movement path geometry."""

    path_id: str
    start_event_id: str
    end_event_id: str
    start_monotonic_ns: int
    end_monotonic_ns: int
    duration_ms: float
    display_id: Optional[str]
    points: list[dict[str, Any]]
    distance_pixels: float
    direction_changes: int
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["point_count"] = len(self.points)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PointerPath":
        return cls(**data)


@dataclass
class ClickInteraction:
    """Physical click relation pairing a down and up event."""

    interaction_id: str
    down_event_id: str
    up_event_id: str
    monotonic_timestamp_ns: int
    relative_time_ms: float
    button: str
    raw_x: float
    raw_y: float
    normalized_x: Optional[float]
    normalized_y: Optional[float]
    display_id: Optional[str]
    duration_ms: float
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ClickInteraction":
        return cls(**data)


@dataclass
class DoubleClickInteraction:
    """Physical double-click pairing two consecutive click interactions."""

    interaction_id: str
    first_click_id: str
    second_click_id: str
    monotonic_timestamp_ns: int
    relative_time_ms: float
    button: str
    raw_x: float
    raw_y: float
    interval_ms: float
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DoubleClickInteraction":
        return cls(**data)


@dataclass
class DragSequence:
    """Physical mouse drag sequence from mouse down to mouse up."""

    sequence_id: str
    down_event_id: str
    up_event_id: str
    movement_event_ids: list[str]
    start_position: tuple[float, float]
    end_position: tuple[float, float]
    start_monotonic_ns: int
    end_monotonic_ns: int
    duration_ms: float
    display_id: Optional[str]
    distance_pixels: float
    provenance: dict[str, Any] = field(default_factory=dict)

    @property
    def start_event_id(self) -> str:
        return self.down_event_id

    @property
    def end_event_id(self) -> str:
        return self.up_event_id

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["start_event_id"] = self.down_event_id
        d["end_event_id"] = self.up_event_id
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DragSequence":
        data_copy = dict(data)
        data_copy.pop("start_event_id", None)
        data_copy.pop("end_event_id", None)
        data_copy["start_position"] = tuple(data_copy["start_position"])
        data_copy["end_position"] = tuple(data_copy["end_position"])
        return cls(**data_copy)


@dataclass
class KeyboardShortcutSequence:
    """Physical keyboard shortcut sequence (modifiers + main key)."""

    sequence_id: str
    event_ids: list[str]
    modifiers: list[str]
    key: str
    monotonic_timestamp_ns: int
    relative_time_ms: float
    duration_ms: float
    keys: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.keys and self.key:
            self.keys = [self.key]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if "keys" not in d or not d["keys"]:
            d["keys"] = [self.key]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KeyboardShortcutSequence":
        data_copy = dict(data)
        if "key" not in data_copy and "keys" in data_copy and data_copy["keys"]:
            data_copy["key"] = data_copy["keys"][0]
        return cls(**data_copy)


@dataclass
class TextInputSequence:
    """Physical text input burst without exposing sensitive raw secrets."""

    sequence_id: str
    event_ids: list[str]
    character_count: int
    text_length: int
    application: Optional[str]
    window_title: Optional[str]
    start_monotonic_ns: int
    end_monotonic_ns: int
    duration_ms: float
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TextInputSequence":
        return cls(**data)


@dataclass
class IdleInterval:
    """Period of physical demonstration inactivity."""

    interval_id: str
    start_monotonic_ns: int
    end_monotonic_ns: int
    duration_ms: float
    duration_ns: int = 0
    preceding_event_id: Optional[str] = None
    succeeding_event_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.duration_ns and self.end_monotonic_ns >= self.start_monotonic_ns:
            self.duration_ns = self.end_monotonic_ns - self.start_monotonic_ns

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if not d.get("duration_ns"):
            d["duration_ns"] = self.end_monotonic_ns - self.start_monotonic_ns
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IdleInterval":
        return cls(**data)


@dataclass
class WindowContextInterval:
    """Active window and application focus duration."""

    interval_id: str
    application: str
    window_title: str
    process_id: Optional[int]
    start_monotonic_ns: int
    end_monotonic_ns: int
    duration_ms: float
    focus_event_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WindowContextInterval":
        return cls(**data)


@dataclass
class ApplicationTransition:
    """Explicit application switch transition."""

    transition_id: str
    from_application: Optional[str]
    to_application: str
    event_id: str
    monotonic_timestamp_ns: int
    relative_time_ms: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApplicationTransition":
        return cls(**data)


class TemporalRelationType(str, Enum):
    """Deterministic temporal relationship types."""

    BEFORE = "BEFORE"
    AFTER = "AFTER"
    OVERLAPS = "OVERLAPS"
    CONTAINS = "CONTAINS"
    DURING = "DURING"
    NEAREST = "NEAREST"
    ADJACENT = "ADJACENT"

    def __str__(self) -> str:
        return self.value


@dataclass
class TemporalRelation:
    """Explicit temporal relationship between two demonstration entities."""

    relation_id: str
    source_id: str
    source_type: str
    target_id: str
    target_type: str
    relation_type: TemporalRelationType
    delta_ms: float
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["relation_type"] = str(self.relation_type)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TemporalRelation":
        data_copy = dict(data)
        data_copy["relation_type"] = TemporalRelationType(data_copy["relation_type"])
        return cls(**data_copy)


@dataclass
class DemonstrationSegment:
    """Bounded, deterministically partitioned demonstration interval."""

    segment_id: str
    sequence: int
    start_monotonic_ns: int
    end_monotonic_ns: int
    start_relative_ms: float
    end_relative_ms: float
    duration_ms: float
    boundary_trigger: str  # e.g. "application_change", "idle_gap", "speech_boundary"
    item_ids: list[str]
    statistics: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ns(self) -> int:
        return max(0, self.end_monotonic_ns - self.start_monotonic_ns)

    @property
    def timeline_item_ids(self) -> list[str]:
        return self.item_ids

    @property
    def event_count(self) -> int:
        return int(self.statistics.get("event_count", len(self.item_ids)))

    @property
    def applications(self) -> list[str]:
        return self.statistics.get("applications", [])

    @property
    def activity_density(self) -> Any:
        class _DensityView:
            def __init__(self, stats: dict[str, Any]):
                self.events_per_second = float(stats.get("activity_density", 0.0))
                self.idle_ratio = float(stats.get("idle_ratio", 0.0))

        return _DensityView(self.statistics)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DemonstrationSegment":
        return cls(**data)


@dataclass
class DemonstrationSummary:
    """Deterministic statistics and activity metrics for demonstration."""

    total_duration_sec: float
    total_canonical_events: int
    events_by_category: dict[str, int]
    total_pointer_paths: int
    total_click_interactions: int
    total_double_clicks: int
    total_drag_sequences: int
    total_keyboard_shortcuts: int
    total_text_inputs: int
    total_segments: int
    total_speech_segments: int
    total_speech_duration_sec: float
    total_annotations: int
    total_frames: int
    distinct_applications: list[str]
    distinct_windows: list[str]
    idle_duration_sec: float
    idle_ratio: float
    activity_density_events_per_sec: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DemonstrationSummary":
        return cls(**data)


@dataclass
class DemonstrationManifest:
    """Metadata manifest defining canonical demonstration representation."""

    demonstration_id: str
    recording_session_id: str
    teaching_session_id: Optional[str] = None
    schema_version: str = "1.0.0"
    derivation_version: str = "phase4-v1"
    algorithm_version: str = "deterministic-v1"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    duration_sec: float = 0.0
    fingerprint: str = ""
    source_checksums: dict[str, str] = field(default_factory=dict)
    hardware_profile: dict[str, Any] = field(default_factory=dict)

    @property
    def representation_fingerprint(self) -> str:
        return self.fingerprint

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DemonstrationManifest":
        return cls(**data)


@dataclass
class FrameItem:
    """Screen checkpoint frame reference."""

    frame_id: str
    monotonic_timestamp: float = 0.0
    timestamp_ns: int = 0
    path: str = ""
    checksum: str = ""
    display_id: str = "0"
    width: int = 1920
    height: int = 1080

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FrameReference:
    """Temporal frame proximity lookup result."""

    before_frame: Optional[FrameItem] = None
    nearest_frame: Optional[FrameItem] = None
    after_frame: Optional[FrameItem] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "before": self.before_frame.to_dict() if self.before_frame else None,
            "nearest": self.nearest_frame.to_dict() if self.nearest_frame else None,
            "after": self.after_frame.to_dict() if self.after_frame else None,
        }

    def __getitem__(self, key: str) -> Any:
        if key in ("before", "before_frame"):
            return self.before_frame.to_dict() if self.before_frame else None
        elif key in ("nearest", "nearest_frame"):
            return self.nearest_frame.to_dict() if self.nearest_frame else None
        elif key in ("after", "after_frame"):
            return self.after_frame.to_dict() if self.after_frame else None
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default


@dataclass
class WindowContextView:
    """Lightweight view for active window context."""

    application_name: str
    window_title: str
    _raw: dict[str, Any] = field(default_factory=dict)

    def __getitem__(self, k: str) -> Any:
        return self._raw[k]

    def get(self, k: str, default: Any = None) -> Any:
        return self._raw.get(k, default)


@dataclass
class DemonstrationContext:
    """Compact context window slice prepared for consumption by future AI models."""

    center_timestamp_ns: int
    window_before_ms: float
    window_after_ms: float
    timeline_items: list[dict[str, Any]]
    events: list[CanonicalEvent]
    frames: list[dict[str, Any]]
    speech_segments: list[dict[str, Any]]
    annotations: list[dict[str, Any]]
    active_window: Optional[dict[str, Any]]
    active_application: Optional[str]
    segment_id: Optional[str]
    relations: list[TemporalRelation]
    demonstration_id: str = ""

    @property
    def window_context(self) -> Optional[WindowContextView]:
        if not self.active_window:
            return None
        app = self.active_window.get("application") or self.active_window.get("app_name") or ""
        win = self.active_window.get("window_title") or self.active_window.get("title") or ""
        return WindowContextView(application_name=app, window_title=win, _raw=self.active_window)

    def to_dict(self) -> dict[str, Any]:
        return {
            "demonstration_id": self.demonstration_id,
            "center_timestamp_ns": self.center_timestamp_ns,
            "window_before_ms": self.window_before_ms,
            "window_after_ms": self.window_after_ms,
            "timeline_items": self.timeline_items,
            "events": [e.to_dict() for e in self.events],
            "frames": self.frames,
            "nearest_frames": self.frames,
            "speech_segments": self.speech_segments,
            "annotations": self.annotations,
            "active_window": self.active_window,
            "active_application": self.active_application,
            "segment_id": self.segment_id,
            "relations": [r.to_dict() for r in self.relations],
        }
