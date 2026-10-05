"""Timeline context data structures representing cross-layer synchronized demonstration state."""

from dataclasses import dataclass, field
from typing import Any, Optional

from teach_a_skill.recorder.events import Event
from teach_a_skill.teaching.annotations.model import TeachingAnnotation
from teach_a_skill.teaching.transcript.segment import TranscriptSegment


@dataclass
class TimelineContext:
    """Synchronized cross-layer snapshot at a given monotonic timestamp."""

    timestamp_monotonic_ns: int
    wall_time: str
    events: list[Event] = field(default_factory=list)
    transcript_segments: list[TranscriptSegment] = field(default_factory=list)
    annotations: list[TeachingAnnotation] = field(default_factory=list)
    nearest_frame: Optional[dict[str, Any]] = None
    active_window: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp_monotonic_ns": self.timestamp_monotonic_ns,
            "wall_time": self.wall_time,
            "events_count": len(self.events),
            "events": [e.to_dict() for e in self.events],
            "transcript_segments": [s.to_dict() for s in self.transcript_segments],
            "annotations": [a.to_dict() for a in self.annotations],
            "nearest_frame": self.nearest_frame,
            "active_window": self.active_window,
        }
