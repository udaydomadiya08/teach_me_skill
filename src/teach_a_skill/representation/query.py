"""Canonical demonstration representation query engine and context window API."""

import bisect
import json
from pathlib import Path
from typing import Any, Optional, Union

from teach_a_skill.core.errors import StorageError
from teach_a_skill.representation.indexes import DemonstrationIndexes
from teach_a_skill.representation.models import (
    CanonicalEvent,
    DemonstrationContext,
    DemonstrationManifest,
    DemonstrationSegment,
    DemonstrationSummary,
    FrameItem,
    FrameReference,
    TemporalRelation,
)
from teach_a_skill.representation.storage import RepresentationStorage
from teach_a_skill.representation.timeline import CanonicalTimelineItem
from teach_a_skill.storage.manager import StorageManager


class RepresentationQueryEngine:
    """High-performance query engine operating over on-disk canonical representations."""

    def __init__(self, storage_manager: StorageManager, recording_session_id: str) -> None:
        self.storage_manager = storage_manager
        self.recording_session_id = recording_session_id
        self.storage = RepresentationStorage(storage_manager, recording_session_id)

        if not self.storage.exists():
            raise StorageError(
                f"Canonical representation for session '{recording_session_id}' not found. "
                "Run 'teach-skill representation build' first."
            )

        # In-memory fast cached metadata and indexes (bounded memory footprint)
        self._manifest: Optional[DemonstrationManifest] = None
        self._summary: Optional[DemonstrationSummary] = None
        self._indexes: Optional[DemonstrationIndexes] = None

        # Lazy caches
        self._timeline_cache: Optional[list[CanonicalTimelineItem]] = None
        self._events_cache: Optional[dict[str, CanonicalEvent]] = None
        self._segments_cache: Optional[list[DemonstrationSegment]] = None
        self._relations_cache: Optional[list[TemporalRelation]] = None
        self._event_id_map: Optional[dict[str, int]] = None

    @property
    def manifest(self) -> DemonstrationManifest:
        if self._manifest is None:
            self._manifest = self.storage.read_manifest()
        return self._manifest

    @property
    def summary(self) -> DemonstrationSummary:
        if self._summary is None:
            self._summary = self.storage.read_summary()
        return self._summary

    @property
    def indexes(self) -> DemonstrationIndexes:
        if self._indexes is None:
            self._indexes = self.storage.read_indexes()
        return self._indexes

    def _ensure_timeline_loaded(self) -> list[CanonicalTimelineItem]:
        if self._timeline_cache is None:
            self._timeline_cache = list(self.storage.stream_timeline_items())
        return self._timeline_cache

    def _ensure_segments_loaded(self) -> list[DemonstrationSegment]:
        if self._segments_cache is None:
            self._segments_cache = list(self.storage.stream_segments())
        return self._segments_cache

    def _ensure_relations_loaded(self) -> list[TemporalRelation]:
        if self._relations_cache is None:
            self._relations_cache = list(self.storage.stream_relations())
        return self._relations_cache

    def _ensure_events_cache(self) -> dict[str, CanonicalEvent]:
        if self._events_cache is None:
            self._events_cache = {}
            for ev in self.storage.stream_canonical_events():
                self._events_cache[ev.event_id] = ev
                self._events_cache[ev.source_event_id] = ev

            if not self._events_cache:
                from teach_a_skill.recorder.storage import SessionStorage

                sess_storage = SessionStorage(self.storage_manager, self.recording_session_id)
                raw_events = sess_storage.read_all_events()
                t0 = raw_events[0].monotonic_timestamp if raw_events else 0.0

                from teach_a_skill.representation.builder import EVENT_TYPE_MAPPING

                for ev in raw_events:
                    rel_sec = max(0.0, ev.monotonic_timestamp - t0)
                    rel_ns = int(rel_sec * 1_000_000_000)
                    c_type, cat = EVENT_TYPE_MAPPING.get(
                        ev.event_type.value,
                        (CanonicalEventType.SYSTEM_WARNING, EventCategory.SYSTEM),
                    )
                    can_ev = CanonicalEvent(
                        event_id=f"canon_evt_{ev.sequence_number:06d}",
                        source_event_id=ev.event_id,
                        timestamp=ev.timestamp,
                        monotonic_timestamp=ev.monotonic_timestamp,
                        relative_time_ms=round(rel_sec * 1000.0, 2),
                        relative_time_ns=rel_ns,
                        category=cat,
                        canonical_event_type=c_type,
                        raw_event_type=ev.event_type.value,
                        source=ev.source,
                        sequence=ev.sequence_number,
                        raw_x=ev.payload.get("x"),
                        raw_y=ev.payload.get("y"),
                        application=ev.payload.get("app_name"),
                        window_title=ev.payload.get("title"),
                        payload=ev.payload,
                        provenance={"session_id": self.recording_session_id},
                    )
                    self._events_cache[can_ev.event_id] = can_ev
                    self._events_cache[can_ev.source_event_id] = can_ev
        return self._events_cache

    # 1. Event queries
    def get_event(self, event_id: str) -> Optional[CanonicalEvent]:
        """Look up canonical event by canonical ID or source event ID.

        Uses the pre-built event_id_map.json index for O(1) lookups without
        loading all events into memory. Falls back to full cache if index is
        unavailable.
        """
        # Fast path: use the event_id_map index for single-event lookup
        if self._events_cache is None:
            # Try index-based lookup first (avoids loading all events)
            if self._event_id_map is None:
                self._event_id_map = self.storage.read_event_id_map()
            if self._event_id_map:
                line_num = self._event_id_map.get(event_id)
                if line_num is not None:
                    ev = self.storage.read_event_at_line(line_num)
                    return ev
                return None

        # Slow path: full cache
        cache = self._ensure_events_cache()
        return cache.get(event_id)

    def get_events(self, start_ns: int, end_ns: int) -> list[CanonicalEvent]:
        """Return all canonical events in monotonic interval [start_ns, end_ns]."""
        items = self.get_timeline_items(start_ns, end_ns)
        events: list[CanonicalEvent] = []
        cache = self._ensure_events_cache()
        for item in items:
            if item.item_type.value == "EVENT":
                ev = cache.get(item.item_id) or cache.get(item.source_id)
                if ev:
                    events.append(ev)
        return events

    # 2. Timeline queries
    def get_timeline_items(self, start_ns: int, end_ns: int) -> list[CanonicalTimelineItem]:
        """Query timeline items in time window."""
        timeline = self._ensure_timeline_loaded()
        if not timeline:
            return []
        keys = [item.monotonic_timestamp_ns for item in timeline]
        idx_start = bisect.bisect_left(keys, start_ns)
        idx_end = bisect.bisect_right(keys, end_ns)
        return timeline[idx_start:idx_end]

    # 3. Segment queries
    def get_segment(self, segment_id: str) -> Optional[DemonstrationSegment]:
        """Look up segment by ID."""
        for seg in self._ensure_segments_loaded():
            if seg.segment_id == segment_id:
                return seg
        return None

    def get_segments(self, start_ns: int, end_ns: int) -> list[DemonstrationSegment]:
        """Return segments overlapping interval [start_ns, end_ns]."""
        results: list[DemonstrationSegment] = []
        for seg in self._ensure_segments_loaded():
            if seg.start_monotonic_ns <= end_ns and seg.end_monotonic_ns >= start_ns:
                results.append(seg)
        return results

    # 4. Relations queries
    def get_relations(self, item_id: str) -> list[TemporalRelation]:
        """Find all relations where item is either source or target."""
        return [
            rel for rel in self._ensure_relations_loaded()
            if rel.source_id == item_id or rel.target_id == item_id
        ]

    # 5. Frames queries
    def get_frames(self, start_ns: int, end_ns: int) -> list[dict[str, Any]]:
        """Return frame references falling within interval."""
        from teach_a_skill.recorder.storage import SessionStorage

        sess_storage = SessionStorage(self.storage_manager, self.recording_session_id)
        frame_index_path = sess_storage.metadata_dir / "frame_index.json"
        if not frame_index_path.exists():
            return []

        data = self.storage_manager.read_metadata(frame_index_path)
        all_frames = data.get("frames", [])
        return [
            f for f in all_frames
            if start_ns <= int(float(f.get("monotonic_timestamp", 0.0)) * 1_000_000_000) <= end_ns
        ]

    def get_nearest_frames(self, event_or_timestamp: Any) -> FrameReference:
        """Return frames immediately before, nearest, and immediately after event or timestamp."""
        if isinstance(event_or_timestamp, (int, float)):
            target_ns = int(event_or_timestamp)
        else:
            ev = self.get_event(str(event_or_timestamp))
            if not ev:
                return FrameReference()
            target_ns = ev.relative_time_ns

        from teach_a_skill.recorder.storage import SessionStorage

        sess_storage = SessionStorage(self.storage_manager, self.recording_session_id)
        frame_index_path = sess_storage.metadata_dir / "frame_index.json"
        if not frame_index_path.exists():
            return FrameReference()

        frames = self.storage_manager.read_metadata(frame_index_path).get("frames", [])
        if not frames:
            return FrameReference()

        frame_times = [
            f.get("timestamp_ns")
            if "timestamp_ns" in f
            else int(float(f.get("monotonic_timestamp", 0.0)) * 1_000_000_000)
            for f in frames
        ]
        idx = bisect.bisect_left(frame_times, target_ns)

        def _to_frame_item(fd: Optional[dict[str, Any]]) -> Optional[FrameItem]:
            if not fd:
                return None
            return FrameItem(
                frame_id=fd.get("frame_id", ""),
                monotonic_timestamp=float(fd.get("monotonic_timestamp", 0.0)),
                timestamp_ns=fd.get("timestamp_ns", 0),
                path=fd.get("path", ""),
                checksum=fd.get("checksum", ""),
                display_id=str(fd.get("display_id", "0")),
                width=int(fd.get("width", 1920)),
                height=int(fd.get("height", 1080)),
            )

        before = frames[idx - 1] if idx > 0 else None
        after = frames[idx] if idx < len(frames) else None

        nearest = None
        if before and after:
            d_b = abs(frame_times[idx - 1] - target_ns)
            d_a = abs(frame_times[idx] - target_ns)
            nearest = before if d_b <= d_a else after
        elif before:
            nearest = before
        elif after:
            nearest = after

        return FrameReference(
            before_frame=_to_frame_item(before),
            nearest_frame=_to_frame_item(nearest),
            after_frame=_to_frame_item(after),
        )

    # 6. Teaching queries
    def get_speech(self, start_ns: int, end_ns: int):
        """Return TranscriptSegment objects overlapping interval."""
        from teach_a_skill.teaching.storage import TeachingStorage

        t_storage = TeachingStorage(self.storage_manager, self.recording_session_id)
        if not t_storage.transcript_file.exists():
            return []
        segments = t_storage.transcript_store.read_all_segments(only_active=True)
        return [
            s for s in segments
            if s.start_monotonic_ns <= end_ns and s.end_monotonic_ns >= start_ns
        ]

    def get_annotations(self, start_ns: int, end_ns: int) -> list[dict[str, Any]]:
        """Return annotations overlapping interval."""
        from teach_a_skill.teaching.storage import TeachingStorage

        t_storage = TeachingStorage(self.storage_manager, self.recording_session_id)
        if not t_storage.annotations_file.exists():
            return []
        anns = t_storage.annotation_store.read_all_annotations(only_active=True)
        return [
            a.to_dict() for a in anns
            if a.start_monotonic_ns <= end_ns and a.end_monotonic_ns >= start_ns
        ]

    # 7. Context queries
    def get_window_context(self, timestamp_ns: int) -> Optional[dict[str, Any]]:
        """Active window title and application at timestamp."""
        timeline = self._ensure_timeline_loaded()
        if not timeline:
            return None
        # Binary search preceding event
        idx = bisect.bisect_right([item.monotonic_timestamp_ns for item in timeline], timestamp_ns)
        for i in range(idx - 1, -1, -1):
            item = timeline[i]
            if item.item_type.value == "EVENT":
                app = item.payload_preview.get("app")
                if app:
                    return {"application": app}
        return None

    def get_application_context(self, timestamp_ns: int) -> Optional[str]:
        """Name of application in focus at timestamp."""
        ctx = self.get_window_context(timestamp_ns)
        return ctx.get("application") if ctx else None

    def get_activity_profile(self, start_ns: int, end_ns: int) -> dict[str, Any]:
        """Compute localized activity metrics in interval."""
        events = self.get_events(start_ns, end_ns)
        dur_sec = max(0.001, (end_ns - start_ns) / 1_000_000_000.0)
        return {
            "duration_sec": round(dur_sec, 2),
            "event_count": len(events),
            "activity_density_events_per_sec": round(len(events) / dur_sec, 2),
            "mouse_events": sum(1 for e in events if e.category.value == "POINTER"),
            "keyboard_events": sum(1 for e in events if e.category.value == "KEYBOARD"),
        }

    # 8. High-Value Context Window API for Future AI
    def get_context_window(
        self,
        center_timestamp_ns: Union[int, str],
        window_before_ms: float = 1500.0,
        window_after_ms: float = 1500.0,
        before_ns: Optional[int] = None,
        after_ns: Optional[int] = None,
    ) -> DemonstrationContext:
        """Core AI API: Slice relevant demonstration context around a milestone.

        Accepts either an integer timestamp in nanoseconds or an event_id string.
        Accepts either window_before_ms/window_after_ms (milliseconds) or
        before_ns/after_ns (nanoseconds) for the window extent.
        """
        if isinstance(center_timestamp_ns, str):
            target_ev = self.get_event(center_timestamp_ns)
            center_timestamp_ns = target_ev.relative_time_ns if target_ev else 0

        if before_ns is not None:
            window_before_ms = before_ns / 1_000_000.0
        if after_ns is not None:
            window_after_ms = after_ns / 1_000_000.0
        start_ns = max(0, int(center_timestamp_ns) - int(window_before_ms * 1_000_000))
        end_ns = int(center_timestamp_ns) + int(window_after_ms * 1_000_000)

        timeline_items = [item.to_dict() for item in self.get_timeline_items(start_ns, end_ns)]
        events = self.get_events(start_ns, end_ns)
        frames = self.get_frames(start_ns, end_ns)
        speech_objs = self.get_speech(start_ns, end_ns)
        speech = [s.to_dict() if hasattr(s, "to_dict") else s for s in speech_objs]
        annotations = self.get_annotations(start_ns, end_ns)
        win_ctx = self.get_window_context(center_timestamp_ns)
        app = win_ctx.get("application") if win_ctx else None

        # Identify segment
        segments = self.get_segments(center_timestamp_ns, center_timestamp_ns)
        seg_id = segments[0].segment_id if segments else None

        # Gather relations touching any event in context
        event_ids = {e.event_id for e in events}
        relations = [
            rel for rel in self._ensure_relations_loaded()
            if rel.source_id in event_ids or rel.target_id in event_ids
        ]

        return DemonstrationContext(
            center_timestamp_ns=center_timestamp_ns,
            window_before_ms=window_before_ms,
            window_after_ms=window_after_ms,
            timeline_items=timeline_items,
            events=events,
            frames=frames,
            speech_segments=speech,
            annotations=annotations,
            active_window=win_ctx,
            active_application=app,
            segment_id=seg_id,
            relations=relations,
            demonstration_id=self.recording_session_id,
        )
