"""Canonical timeline model with strict deterministic monotonic ordering."""

import bisect
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional, Union


class TimelineItemType(str, Enum):
    """Canonical timeline entity types."""

    EVENT = "EVENT"
    FRAME = "FRAME"
    WINDOW_CONTEXT = "WINDOW_CONTEXT"
    AUDIO = "AUDIO"
    SPEECH = "SPEECH"
    ANNOTATION = "ANNOTATION"

    def __str__(self) -> str:
        return self.value


PRIORITY_RANKS: dict[str, int] = {
    TimelineItemType.EVENT.value: 2,
    TimelineItemType.FRAME.value: 3,
    TimelineItemType.SPEECH.value: 4,
    TimelineItemType.ANNOTATION.value: 5,
    TimelineItemType.WINDOW_CONTEXT.value: 6,
    TimelineItemType.AUDIO.value: 7,
}


@dataclass(frozen=True)
class CanonicalTimelineItem:
    """Single item on the canonical unified timeline."""

    item_id: str
    item_type: TimelineItemType
    source_id: str
    monotonic_timestamp_ns: int
    relative_time_ms: float
    sequence: int
    priority_rank: int = field(default=2)
    payload_preview: dict[str, Any] = field(default_factory=dict)

    @property
    def relative_time_ns(self) -> int:
        return self.monotonic_timestamp_ns

    def sort_key(self) -> tuple[int, int, int, str]:
        """Deterministic tie-breaking key:

        Primary: Monotonic timestamp (nanoseconds)
        Secondary: Entity priority rank
        Tertiary: Original recording sequence number
        Quaternary: Stable entity ID
        """
        return (
            self.monotonic_timestamp_ns,
            self.priority_rank,
            self.sequence,
            self.item_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "item_type": str(self.item_type),
            "source_id": self.source_id,
            "monotonic_timestamp_ns": self.monotonic_timestamp_ns,
            "relative_time_ms": self.relative_time_ms,
            "sequence": self.sequence,
            "priority_rank": self.priority_rank,
            "payload_preview": self.payload_preview,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CanonicalTimelineItem":
        data_copy = dict(data)
        data_copy["item_type"] = TimelineItemType(data_copy["item_type"])
        return cls(**data_copy)


class CanonicalTimeline:
    """Ordered chronological index of all demonstration entities."""

    def __init__(
        self,
        session_id_or_items: "Optional[Union[str, list[CanonicalTimelineItem]]]" = None,
    ) -> None:
        # Accept either a session_id string (ignored, for API compat) or a list of items
        if isinstance(session_id_or_items, str):
            initial_items: list[CanonicalTimelineItem] = []
        elif isinstance(session_id_or_items, list):
            initial_items = session_id_or_items
        elif session_id_or_items is None:
            initial_items = []
        else:
            initial_items = list(session_id_or_items)

        self._items: list[CanonicalTimelineItem] = sorted(
            initial_items,
            key=lambda x: x.sort_key(),
        )
        self._rebuild_indexes()

    def _rebuild_indexes(self) -> None:
        self._keys_ns = [item.monotonic_timestamp_ns for item in self._items]
        self._id_map = {item.item_id: idx for idx, item in enumerate(self._items)}

    def add_item(
        self,
        item_type: TimelineItemType,
        item_id: str,
        source_id: str,
        timestamp_ns: int,
        monotonic_timestamp_ns: int,
        relative_time_ns: int,
        sequence: int,
        priority_rank: int = 2,
        payload_preview: Optional[dict] = None,
    ) -> None:
        """Add a single item to the timeline (triggers re-sort)."""
        relative_time_ms = round(relative_time_ns / 1_000_000.0, 2)
        item = CanonicalTimelineItem(
            item_id=item_id,
            item_type=item_type,
            source_id=source_id,
            monotonic_timestamp_ns=monotonic_timestamp_ns,
            relative_time_ms=relative_time_ms,
            sequence=sequence,
            priority_rank=priority_rank,
            payload_preview=payload_preview or {},
        )
        import bisect
        insert_idx = bisect.bisect_right(self._keys_ns, monotonic_timestamp_ns)
        self._items.insert(insert_idx, item)
        self._rebuild_indexes()

    def get_sorted_items(self) -> list[CanonicalTimelineItem]:
        """Return all items sorted by deterministic sort key."""
        return sorted(self._items, key=lambda x: x.sort_key())

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, idx: Any) -> Any:
        return self._items[idx]

    def __iter__(self):
        return iter(self._items)

    @property
    def items(self) -> list[CanonicalTimelineItem]:
        return list(self._items)

    def get_items_between(
        self, start_mono_ns: int, end_mono_ns: int
    ) -> list[CanonicalTimelineItem]:
        """Return items falling strictly within [start_mono_ns, end_mono_ns]."""
        if not self._keys_ns or start_mono_ns > end_mono_ns:
            return []

        idx_start = bisect.bisect_left(self._keys_ns, start_mono_ns)
        idx_end = bisect.bisect_right(self._keys_ns, end_mono_ns)
        return self._items[idx_start:idx_end]

    def get_nearest_item(
        self, mono_ns: int, item_type: Optional[TimelineItemType] = None
    ) -> Optional[CanonicalTimelineItem]:
        """Return the closest item to given timestamp, optionally filtered by type."""
        candidates = (
            [item for item in self._items if item.item_type == item_type]
            if item_type
            else self._items
        )
        if not candidates:
            return None

        keys = [item.monotonic_timestamp_ns for item in candidates]
        idx = bisect.bisect_left(keys, mono_ns)

        if idx == 0:
            return candidates[0]
        if idx >= len(candidates):
            return candidates[-1]

        before = candidates[idx - 1]
        after = candidates[idx]
        diff_before = abs(before.monotonic_timestamp_ns - mono_ns)
        diff_after = abs(after.monotonic_timestamp_ns - mono_ns)
        return before if diff_before <= diff_after else after

    def get_item_by_id(self, item_id: str) -> Optional[CanonicalTimelineItem]:
        """Fast O(1) lookup of timeline item by ID."""
        idx = self._id_map.get(item_id)
        if idx is not None and 0 <= idx < len(self._items):
            return self._items[idx]
        return None

