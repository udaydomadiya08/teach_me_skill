"""Deterministic timeline synchronization engine fusing physical demonstration events and teaching evidence."""

import bisect
from datetime import datetime, timezone
from typing import Any, Optional

from teach_a_skill.recorder.events import Event
from teach_a_skill.teaching.annotations.model import TeachingAnnotation
from teach_a_skill.teaching.audio.wav import AudioChunk
from teach_a_skill.teaching.timeline.context import TimelineContext
from teach_a_skill.teaching.transcript.segment import TranscriptSegment


class TeachingTimelineEngine:
    """Fuses Phase 2 raw evidence with Phase 3 teaching audio, transcript, and annotations."""

    def __init__(
        self,
        events: Optional[list[Event]] = None,
        transcript_segments: Optional[list[TranscriptSegment]] = None,
        annotations: Optional[list[TeachingAnnotation]] = None,
        frame_index: Optional[dict[str, Any]] = None,
        audio_chunks: Optional[list[AudioChunk]] = None,
    ) -> None:
        self.events = sorted(events or [], key=lambda e: e.monotonic_timestamp)
        self.transcript_segments = sorted(
            [s for s in (transcript_segments or []) if s.is_active],
            key=lambda s: s.start_monotonic_ns,
        )
        self.annotations = sorted(
            [a for a in (annotations or []) if a.is_active],
            key=lambda a: a.start_monotonic_ns,
        )
        self.frames = frame_index.get("frames", []) if frame_index else []
        self.audio_chunks = sorted(audio_chunks or [], key=lambda c: c.start_monotonic_ns)

        # Monotonic time keys in nanoseconds for binary search
        self._event_keys_ns = [int(e.monotonic_timestamp * 1_000_000_000) for e in self.events]
        self._transcript_start_keys_ns = [s.start_monotonic_ns for s in self.transcript_segments]
        self._annotation_start_keys_ns = [a.start_monotonic_ns for a in self.annotations]
        self._frame_keys_ns = [
            int(f.get("monotonic_timestamp", 0.0) * 1_000_000_000) for f in self.frames
        ]

    def get_events_between(self, start_mono_ns: int, end_mono_ns: int) -> list[Event]:
        """Return all physical events occurring within the monotonic nanosecond interval [start, end]."""
        if not self._event_keys_ns or start_mono_ns > end_mono_ns:
            return []

        idx_start = bisect.bisect_left(self._event_keys_ns, start_mono_ns)
        idx_end = bisect.bisect_right(self._event_keys_ns, end_mono_ns)
        return self.events[idx_start:idx_end]

    def get_transcript_between(
        self, start_mono_ns: int, end_mono_ns: int
    ) -> list[TranscriptSegment]:
        """Return transcript segments overlapping the monotonic nanosecond interval [start, end]."""
        results: list[TranscriptSegment] = []
        for seg in self.transcript_segments:
            # Overlap condition: seg.start <= end and seg.end >= start
            if seg.start_monotonic_ns <= end_mono_ns and seg.end_monotonic_ns >= start_mono_ns:
                results.append(seg)
        return results

    def get_annotations_between(
        self, start_mono_ns: int, end_mono_ns: int
    ) -> list[TeachingAnnotation]:
        """Return annotations overlapping the monotonic nanosecond interval [start, end]."""
        results: list[TeachingAnnotation] = []
        for ann in self.annotations:
            if ann.start_monotonic_ns <= end_mono_ns and ann.end_monotonic_ns >= start_mono_ns:
                results.append(ann)
        return results

    def get_nearest_frame(self, mono_ns: int) -> Optional[dict[str, Any]]:
        """Return screen frame closest in time to given monotonic timestamp."""
        if not self.frames:
            return None

        idx = bisect.bisect_left(self._frame_keys_ns, mono_ns)
        if idx == 0:
            return self.frames[0]
        if idx >= len(self.frames):
            return self.frames[-1]

        before = self.frames[idx - 1]
        after = self.frames[idx]
        diff_before = abs(self._frame_keys_ns[idx - 1] - mono_ns)
        diff_after = abs(self._frame_keys_ns[idx] - mono_ns)
        return before if diff_before <= diff_after else after

    def get_active_window_at(self, mono_ns: int) -> Optional[dict[str, Any]]:
        """Return active window context immediately preceding or at given timestamp."""
        if not self.events:
            return None

        idx = bisect.bisect_right(self._event_keys_ns, mono_ns)
        for i in range(idx - 1, -1, -1):
            e = self.events[i]
            if e.event_type.value == "WINDOW_FOCUS_CHANGED":
                return e.payload
        return None

    def get_context_at(self, mono_ns: int, window_ns: int = 500_000_000) -> TimelineContext:
        """Construct full TimelineContext around timestamp +/- window_ns (default +/- 500ms)."""
        start_ns = max(0, mono_ns - window_ns)
        end_ns = mono_ns + window_ns

        events = self.get_events_between(start_ns, end_ns)
        transcript = self.get_transcript_between(start_ns, end_ns)
        annotations = self.get_annotations_between(start_ns, end_ns)
        nearest_frame = self.get_nearest_frame(mono_ns)
        active_window = self.get_active_window_at(mono_ns)

        now_wall = datetime.now(timezone.utc).isoformat()

        return TimelineContext(
            timestamp_monotonic_ns=mono_ns,
            wall_time=now_wall,
            events=events,
            transcript_segments=transcript,
            annotations=annotations,
            nearest_frame=nearest_frame,
            active_window=active_window,
        )

    def get_events_for_speech_segment(self, segment_id: str) -> list[Event]:
        """Return all raw events occurring during a specific spoken sentence/segment."""
        seg = next((s for s in self.transcript_segments if s.segment_id == segment_id), None)
        if not seg:
            return []
        return self.get_events_between(seg.start_monotonic_ns, seg.end_monotonic_ns)

    def get_speech_for_event(self, event_id: str) -> list[TranscriptSegment]:
        """Return spoken transcript segments overlapping or surrounding a specific event."""
        evt = next((e for e in self.events if e.event_id == event_id), None)
        if not evt:
            return []
        evt_ns = int(evt.monotonic_timestamp * 1_000_000_000)
        # Search within 1 second window
        return self.get_transcript_between(evt_ns - 1_000_000_000, evt_ns + 1_000_000_000)

    def get_annotations_for_event(self, event_id: str) -> list[TeachingAnnotation]:
        """Return annotations referencing or temporally overlapping a specific event."""
        matching: list[TeachingAnnotation] = []
        for ann in self.annotations:
            ref_events = ann.references.get("event_ids", [])
            if event_id in ref_events:
                matching.append(ann)

        if not matching:
            evt = next((e for e in self.events if e.event_id == event_id), None)
            if evt:
                evt_ns = int(evt.monotonic_timestamp * 1_000_000_000)
                matching = self.get_annotations_between(
                    evt_ns - 1_000_000_000, evt_ns + 1_000_000_000
                )

        return matching

    def get_unified_stream(self) -> list[dict[str, Any]]:
        """Return all events, speech segments, annotations, and screen frames in strict temporal order."""
        items: list[dict[str, Any]] = []

        for e in self.events:
            items.append(
                {
                    "type": "event",
                    "subtype": e.event_type.value,
                    "id": e.event_id,
                    "timestamp_ns": int(e.monotonic_timestamp * 1_000_000_000),
                    "item": e,
                }
            )

        for s in self.transcript_segments:
            items.append(
                {
                    "type": "speech",
                    "subtype": "transcript_segment",
                    "id": s.segment_id,
                    "timestamp_ns": s.start_monotonic_ns,
                    "item": s,
                }
            )

        for a in self.annotations:
            items.append(
                {
                    "type": "annotation",
                    "subtype": a.type.value,
                    "id": a.annotation_id,
                    "timestamp_ns": a.start_monotonic_ns,
                    "item": a,
                }
            )

        for f in self.frames:
            ts_ns = int(f.get("monotonic_timestamp", 0.0) * 1_000_000_000)
            items.append(
                {
                    "type": "screen_frame",
                    "subtype": "frame",
                    "id": f.get("frame_id", ""),
                    "timestamp_ns": ts_ns,
                    "item": f,
                }
            )

        return sorted(items, key=lambda x: x["timestamp_ns"])
