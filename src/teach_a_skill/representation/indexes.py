"""Compact local indexing for canonical demonstration query optimization."""

import bisect
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class DemonstrationIndexes:
    """Pre-computed local indexes accelerating temporal and identity lookups."""

    # Time to timeline item index: sorted list of [monotonic_timestamp_ns, timeline_item_index]
    time_to_timeline: list[list[int]] = field(default_factory=list)
    # Entity ID -> timeline item index
    id_to_timeline_index: dict[str, int] = field(default_factory=dict)
    # Segment ID -> [start_ns, end_ns, start_timeline_idx, end_timeline_idx]
    segment_ranges: dict[str, list[int]] = field(default_factory=dict)
    # Application name -> list of [start_ns, end_ns]
    app_to_intervals: dict[str, list[list[int]]] = field(default_factory=dict)
    # Window title -> list of [start_ns, end_ns]
    window_to_intervals: dict[str, list[list[int]]] = field(default_factory=dict)
    # Frame ID -> monotonic_timestamp_ns
    frame_to_time_ns: dict[str, int] = field(default_factory=dict)
    # Speech segment ID -> monotonic_timestamp_ns
    speech_to_time_ns: dict[str, int] = field(default_factory=dict)
    # Annotation ID -> monotonic_timestamp_ns
    annotation_to_time_ns: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DemonstrationIndexes":
        return cls(**data)

    def save(self, target_file: Path) -> None:
        """Atomically persist indexes to disk."""
        target_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_file = target_file.with_suffix(".tmp")
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, separators=(",", ":"))
        tmp_file.replace(target_file)

    @classmethod
    def load(cls, target_file: Path) -> "DemonstrationIndexes":
        """Load pre-computed indexes from disk."""
        if not target_file.exists():
            return cls()
        with open(target_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    def find_timeline_index_at_time(self, monotonic_ns: int) -> int:
        """Binary search closest timeline index for timestamp."""
        if not self.time_to_timeline:
            return 0
        keys = [entry[0] for entry in self.time_to_timeline]
        idx = bisect.bisect_left(keys, monotonic_ns)
        if idx >= len(keys):
            return self.time_to_timeline[-1][1]
        return self.time_to_timeline[idx][1]

    def find_timeline_index_by_id(self, item_id: str) -> Optional[int]:
        """O(1) lookup of timeline index by entity ID."""
        return self.id_to_timeline_index.get(item_id)
