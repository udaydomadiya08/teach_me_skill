"""Tests for Phase 3 Teaching Timeline synchronization engine."""

from teach_a_skill.recorder.events import Event, EventPriority, EventType
from teach_a_skill.teaching.annotations.model import AnnotationType, TeachingAnnotation
from teach_a_skill.teaching.timeline.context import TimelineContext
from teach_a_skill.teaching.timeline.engine import TeachingTimelineEngine
from teach_a_skill.teaching.transcript.segment import TranscriptSegment


def _make_event(evt_id: str, mono_sec: float, event_type: EventType, payload: dict = None) -> Event:
    return Event(
        event_id=evt_id,
        session_id="sesh_timeline",
        sequence_number=1,
        timestamp="2026-10-04T12:00:00Z",
        monotonic_timestamp=mono_sec,
        event_type=event_type,
        priority=EventPriority.MEDIUM,
        source="system",
        payload=payload or {},
    )


def test_timeline_engine_cross_layer_queries():
    """Test unified cross-layer timeline queries with events, transcripts, annotations, and frames."""
    # 0s: Mouse move
    # 1.0s: Mouse click (evt_click)
    # 1.5s - 3.5s: Spoken words "Now I open the settings menu" (seg_01)
    # 2.0s: Window focus changed to "Settings"
    # 2.5s: Annotation "Click here to see preferences" referencing evt_click
    # 4.0s: Keyboard shortcut
    events = [
        _make_event("evt_01", 0.0, EventType.MOUSE_MOVE, {"x": 100, "y": 100}),
        _make_event(
            "evt_click", 1.0, EventType.MOUSE_CLICK, {"button": "left", "x": 105, "y": 105}
        ),
        _make_event(
            "evt_focus",
            2.0,
            EventType.WINDOW_FOCUS_CHANGED,
            {"app_name": "Settings", "title": "Preferences"},
        ),
        _make_event("evt_key", 4.0, EventType.KEY_DOWN, {"key": "Enter"}),
    ]

    segments = [
        TranscriptSegment(
            segment_id="seg_01",
            teaching_session_id="teach_sesh",
            sequence_number=1,
            start_monotonic_ns=1_500_000_000,
            end_monotonic_ns=3_500_000_000,
            start_wall_time="2026-10-04T12:00:01.5Z",
            end_wall_time="2026-10-04T12:00:03.5Z",
            text="Now I open the settings menu",
            language="en",
            confidence=0.95,
            source="local_stt",
            audio_chunk_ids=["chk_01"],
        )
    ]

    annotations = [
        TeachingAnnotation(
            annotation_id="ann_01",
            teaching_session_id="teach_sesh",
            created_monotonic_ns=2_500_000_000,
            start_monotonic_ns=2_500_000_000,
            end_monotonic_ns=3_000_000_000,
            text="Click here to see preferences",
            type=AnnotationType.INSTRUCTION,
            references={"event_ids": ["evt_click"]},
        )
    ]

    frame_index = {
        "frames": [
            {"frame_id": "f_0", "monotonic_timestamp": 0.0, "path": "frames/f_0.webp"},
            {"frame_id": "f_1", "monotonic_timestamp": 1.2, "path": "frames/f_1.webp"},
            {"frame_id": "f_2", "monotonic_timestamp": 3.0, "path": "frames/f_2.webp"},
        ]
    }

    engine = TeachingTimelineEngine(
        events=events,
        transcript_segments=segments,
        annotations=annotations,
        frame_index=frame_index,
    )

    # 1. Query events during speech segment
    evts_during_speech = engine.get_events_for_speech_segment("seg_01")
    assert len(evts_during_speech) == 1
    assert evts_during_speech[0].event_id == "evt_focus"

    # 2. Query speech during/surrounding click event
    speech_near_click = engine.get_speech_for_event("evt_click")
    assert len(speech_near_click) == 1
    assert speech_near_click[0].segment_id == "seg_01"

    # 3. Query annotations referencing click event
    anns_for_click = engine.get_annotations_for_event("evt_click")
    assert len(anns_for_click) == 1
    assert anns_for_click[0].annotation_id == "ann_01"

    # 4. Query nearest frame
    # At 1.1s, frame at 1.2s is closest
    nearest_frame = engine.get_nearest_frame(1_100_000_000)
    assert nearest_frame["frame_id"] == "f_1"

    # At 2.8s, frame at 3.0s is closest
    nearest_frame_2 = engine.get_nearest_frame(2_800_000_000)
    assert nearest_frame_2["frame_id"] == "f_2"

    # 5. Query active window at 2.5s (should be Settings)
    active_win = engine.get_active_window_at(2_500_000_000)
    assert active_win["app_name"] == "Settings"

    # 6. Unified TimelineContext at 2.0s (+/- 600ms)
    context = engine.get_context_at(2_000_000_000, window_ns=600_000_000)
    assert isinstance(context, TimelineContext)
    assert len(context.events) == 1  # evt_focus at 2.0s
    assert len(context.transcript_segments) == 1  # seg_01 overlaps 1.5 - 3.5s
    assert len(context.annotations) == 1  # ann_01 at 2.5s is within 2.0s +/- 600ms
    assert context.active_window["app_name"] == "Settings"


def test_timeline_engine_empty():
    """Test timeline queries with no recorded events or speech."""
    engine = TeachingTimelineEngine()
    assert engine.get_events_between(0, 1000) == []
    assert engine.get_transcript_between(0, 1000) == []
    assert engine.get_annotations_between(0, 1000) == []
    assert engine.get_nearest_frame(500) is None
    assert engine.get_active_window_at(500) is None

    context = engine.get_context_at(1_000_000_000)
    assert context.events == []
    assert context.transcript_segments == []
    assert context.annotations == []
    assert context.nearest_frame is None
