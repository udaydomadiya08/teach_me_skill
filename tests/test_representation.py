"""Comprehensive test suite for Phase 4: Canonical Event Timeline & Demonstration Representation.

Verifies:
- Lossless canonical normalization (coordinates, relative timestamps, categories)
- Derived physical interactions (clicks, double-clicks, drags, pointer paths, shortcuts, text sequences, idles)
- Deterministic temporal relation graph (BEFORE, AFTER, CONTAINS, OVERLAPS, NEAREST)
- Unified canonical timeline with deterministic tie-breaking
- Deterministic segmentation & activity density metrics
- Local compact indexing and high-value AI Context Window API
- Raw evidence immutability (Phase 2 & Phase 3 hashes unchanged)
- Semantic non-inference verification (pure physical evidence; no task/intent/UI meaning fabricated)
- Provenance tracing (every canonical & derived item traces to raw source IDs)
- Representation validator, atomic build, fingerprinting, and cache
- Scalability on large demonstration sessions
"""

import hashlib
import json
import time
from pathlib import Path

import pytest

from teach_a_skill.recorder.events import Event, EventPriority, EventType
from teach_a_skill.recorder.session import RecordingSession, SessionState
from teach_a_skill.recorder.storage import SessionStorage
from teach_a_skill.representation.builder import RepresentationBuilder
from teach_a_skill.representation.demonstration import Demonstration
from teach_a_skill.representation.derivation.interactions import (
    derive_click_interactions,
    derive_drag_sequences,
    derive_keyboard_shortcuts,
    derive_pointer_paths,
    derive_text_input_sequences,
)
from teach_a_skill.representation.derivation.relations import build_temporal_relations
from teach_a_skill.representation.derivation.segmentation import derive_demonstration_segments
from teach_a_skill.representation.fingerprint import compute_demonstration_fingerprint
from teach_a_skill.representation.models import (
    CanonicalEventType,
    DemonstrationContext,
    EventCategory,
    TemporalRelation,
    TemporalRelationType,
)
from teach_a_skill.representation.query import RepresentationQueryEngine
from teach_a_skill.representation.storage import RepresentationStorage
from teach_a_skill.representation.timeline import CanonicalTimeline, TimelineItemType
from teach_a_skill.representation.validator import RepresentationValidator
from teach_a_skill.storage.manager import StorageManager
from teach_a_skill.teaching.annotations.model import AnnotationType, TeachingAnnotation
from teach_a_skill.teaching.storage import TeachingStorage
from teach_a_skill.teaching.transcript.segment import TranscriptSegment


def _create_full_test_session(storage_manager: StorageManager, session_id: str) -> Path:
    """Create an authoritative Phase 2 + Phase 3 session with rich multi-modal physical evidence."""
    session_storage = SessionStorage(storage_manager, session_id)
    session = RecordingSession(
        session_id=session_id,
        platform_name="darwin",
        architecture="arm64",
    )
    session_storage.initialize_session_layout(session.manifest)

    # 1. Phase 2 Events
    base_ns = 1_000_000_000
    events = [
        # Window focus
        Event(
            event_id="evt_01",
            session_id=session_id,
            sequence_number=1,
            timestamp="2026-10-04T12:00:00.000Z",
            monotonic_timestamp=1.0,
            event_type=EventType.WINDOW_FOCUS_CHANGED,
            priority=EventPriority.HIGH,
            source="window",
            payload={"app_name": "TextEdit", "title": "Untitled.txt", "display_id": "disp_0"},
        ),
        # Mouse movement sequence
        Event(
            event_id="evt_02",
            session_id=session_id,
            sequence_number=2,
            timestamp="2026-10-04T12:00:00.100Z",
            monotonic_timestamp=1.1,
            event_type=EventType.MOUSE_MOVE,
            priority=EventPriority.LOW,
            source="mouse",
            payload={"x": 100, "y": 100, "display_id": "disp_0"},
        ),
        Event(
            event_id="evt_03",
            session_id=session_id,
            sequence_number=3,
            timestamp="2026-10-04T12:00:00.200Z",
            monotonic_timestamp=1.2,
            event_type=EventType.MOUSE_MOVE,
            priority=EventPriority.LOW,
            source="mouse",
            payload={"x": 120, "y": 110, "display_id": "disp_0"},
        ),
        Event(
            event_id="evt_04",
            session_id=session_id,
            sequence_number=4,
            timestamp="2026-10-04T12:00:00.300Z",
            monotonic_timestamp=1.3,
            event_type=EventType.MOUSE_MOVE,
            priority=EventPriority.LOW,
            source="mouse",
            payload={"x": 150, "y": 120, "display_id": "disp_0"},
        ),
        # Click (down + up)
        Event(
            event_id="evt_05",
            session_id=session_id,
            sequence_number=5,
            timestamp="2026-10-04T12:00:00.400Z",
            monotonic_timestamp=1.4,
            event_type=EventType.MOUSE_DOWN,
            priority=EventPriority.CRITICAL,
            source="mouse",
            payload={"button": "left", "x": 150, "y": 120, "display_id": "disp_0"},
        ),
        Event(
            event_id="evt_06",
            session_id=session_id,
            sequence_number=6,
            timestamp="2026-10-04T12:00:00.450Z",
            monotonic_timestamp=1.45,
            event_type=EventType.MOUSE_UP,
            priority=EventPriority.CRITICAL,
            source="mouse",
            payload={"button": "left", "x": 150, "y": 120, "display_id": "disp_0"},
        ),
        # Physical Drag sequence (down -> move -> move -> up)
        Event(
            event_id="evt_07",
            session_id=session_id,
            sequence_number=7,
            timestamp="2026-10-04T12:00:01.000Z",
            monotonic_timestamp=2.0,
            event_type=EventType.MOUSE_DOWN,
            priority=EventPriority.CRITICAL,
            source="mouse",
            payload={"button": "left", "x": 200, "y": 200, "display_id": "disp_0"},
        ),
        Event(
            event_id="evt_08",
            session_id=session_id,
            sequence_number=8,
            timestamp="2026-10-04T12:00:01.100Z",
            monotonic_timestamp=2.1,
            event_type=EventType.MOUSE_MOVE,
            priority=EventPriority.LOW,
            source="mouse",
            payload={"x": 250, "y": 250, "display_id": "disp_0"},
        ),
        Event(
            event_id="evt_09",
            session_id=session_id,
            sequence_number=9,
            timestamp="2026-10-04T12:00:01.200Z",
            monotonic_timestamp=2.2,
            event_type=EventType.MOUSE_MOVE,
            priority=EventPriority.LOW,
            source="mouse",
            payload={"x": 300, "y": 300, "display_id": "disp_0"},
        ),
        Event(
            event_id="evt_10",
            session_id=session_id,
            sequence_number=10,
            timestamp="2026-10-04T12:00:01.300Z",
            monotonic_timestamp=2.3,
            event_type=EventType.MOUSE_UP,
            priority=EventPriority.CRITICAL,
            source="mouse",
            payload={"button": "left", "x": 300, "y": 300, "display_id": "disp_0"},
        ),
        # Physical Keyboard shortcut: CTRL+C (ctrl_down -> c_down -> c_up -> ctrl_up)
        Event(
            event_id="evt_11",
            session_id=session_id,
            sequence_number=11,
            timestamp="2026-10-04T12:00:02.000Z",
            monotonic_timestamp=3.0,
            event_type=EventType.KEY_DOWN,
            priority=EventPriority.HIGH,
            source="keyboard",
            payload={"key": "ctrl", "is_modifier": True},
        ),
        Event(
            event_id="evt_12",
            session_id=session_id,
            sequence_number=12,
            timestamp="2026-10-04T12:00:02.050Z",
            monotonic_timestamp=3.05,
            event_type=EventType.KEY_DOWN,
            priority=EventPriority.CRITICAL,
            source="keyboard",
            payload={"key": "c", "is_modifier": False},
        ),
        Event(
            event_id="evt_13",
            session_id=session_id,
            sequence_number=13,
            timestamp="2026-10-04T12:00:02.100Z",
            monotonic_timestamp=3.10,
            event_type=EventType.KEY_UP,
            priority=EventPriority.HIGH,
            source="keyboard",
            payload={"key": "c", "is_modifier": False},
        ),
        Event(
            event_id="evt_14",
            session_id=session_id,
            sequence_number=14,
            timestamp="2026-10-04T12:00:02.150Z",
            monotonic_timestamp=3.15,
            event_type=EventType.KEY_UP,
            priority=EventPriority.HIGH,
            source="keyboard",
            payload={"key": "ctrl", "is_modifier": True},
        ),
        # Text input sequence: "h", "i"
        Event(
            event_id="evt_15",
            session_id=session_id,
            sequence_number=15,
            timestamp="2026-10-04T12:00:02.300Z",
            monotonic_timestamp=3.30,
            event_type=EventType.KEY_DOWN,
            priority=EventPriority.HIGH,
            source="keyboard",
            payload={"key": "h"},
        ),
        Event(
            event_id="evt_16",
            session_id=session_id,
            sequence_number=16,
            timestamp="2026-10-04T12:00:02.400Z",
            monotonic_timestamp=3.40,
            event_type=EventType.KEY_DOWN,
            priority=EventPriority.HIGH,
            source="keyboard",
            payload={"key": "i"},
        ),
        # Application switch: to Terminal
        Event(
            event_id="evt_17",
            session_id=session_id,
            sequence_number=17,
            timestamp="2026-10-04T12:00:03.000Z",
            monotonic_timestamp=4.0,
            event_type=EventType.WINDOW_FOCUS_CHANGED,
            priority=EventPriority.HIGH,
            source="window",
            payload={"app_name": "Terminal", "title": "bash", "display_id": "disp_0"},
        ),
        # Idle period gap until 9.0s (5.0s idle gap > 4.0s threshold)
        Event(
            event_id="evt_18",
            session_id=session_id,
            sequence_number=18,
            timestamp="2026-10-04T12:00:08.000Z",
            monotonic_timestamp=9.0,
            event_type=EventType.KEY_DOWN,
            priority=EventPriority.HIGH,
            source="keyboard",
            payload={"key": "enter"},
        ),
    ]
    for evt in events:
        session_storage.append_event(evt)

    # 2. Screen frames
    frames_meta = {
        "frames": [
            {
                "frame_id": "frame_01",
                "monotonic_timestamp": 1.0,
                "timestamp_ns": base_ns,
                "path": "frames/frame_01.webp",
                "checksum": "abc1",
                "display_id": "disp_0",
                "width": 1920,
                "height": 1080,
            },
            {
                "frame_id": "frame_02",
                "monotonic_timestamp": 2.0,
                "timestamp_ns": base_ns + 1_000_000_000,
                "path": "frames/frame_02.webp",
                "checksum": "abc2",
                "display_id": "disp_0",
                "width": 1920,
                "height": 1080,
            },
            {
                "frame_id": "frame_03",
                "monotonic_timestamp": 4.0,
                "timestamp_ns": base_ns + 3_000_000_000,
                "path": "frames/frame_03.webp",
                "checksum": "abc3",
                "display_id": "disp_0",
                "width": 1920,
                "height": 1080,
            },
        ]
    }
    session_storage.storage_manager.write_metadata(
        session_storage.metadata_dir / "frame_index.json", frames_meta
    )

    # Create dummy frame files to satisfy reference verification
    for f in frames_meta["frames"]:
        fpath = session_storage.session_dir / f["path"]
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_bytes(b"RIFF\x00\x00\x00\x00WEBPVP8L")

    session.transition_to(SessionState.RECORDING)
    session.transition_to(SessionState.STOPPING)
    session.transition_to(SessionState.COMPLETED)
    session_storage.finalize_session(
        session.manifest,
        {"events_count": len(events), "frames_count": 3, "completed_at": "2026-10-04T12:00:09Z"},
        frames_meta,
    )

    # 3. Phase 3 Teaching Layer Evidence
    from teach_a_skill.teaching.session import TeachingManifest, TeachingState

    teaching_storage = TeachingStorage(storage_manager, session_id)
    teaching_manifest = TeachingManifest(
        teaching_session_id=f"teach_{session_id}",
        recording_session_id=session_id,
        status=TeachingState.COMPLETED,
    )
    teaching_storage.initialize_teaching_layout(teaching_manifest)

    # Speech transcript segments
    t_seg1 = TranscriptSegment(
        segment_id="sp_01",
        teaching_session_id=session_id,
        sequence_number=1,
        start_monotonic_ns=base_ns + 300_000_000,  # 1.3s
        end_monotonic_ns=base_ns + 600_000_000,  # 1.6s
        start_wall_time="2026-10-04T12:00:01.300Z",
        end_wall_time="2026-10-04T12:00:01.600Z",
        text="Click the document area",
        confidence=0.98,
    )
    t_seg2 = TranscriptSegment(
        segment_id="sp_02",
        teaching_session_id=session_id,
        sequence_number=2,
        start_monotonic_ns=base_ns + 1_900_000_000,  # 2.9s
        end_monotonic_ns=base_ns + 2_200_000_000,  # 3.2s
        start_wall_time="2026-10-04T12:00:02.900Z",
        end_wall_time="2026-10-04T12:00:03.200Z",
        text="Copy the selected line",
        confidence=0.95,
    )
    teaching_storage.transcript_store.append_segment(t_seg1)
    teaching_storage.transcript_store.append_segment(t_seg2)

    # User text annotation
    ann1 = TeachingAnnotation(
        annotation_id="ann_01",
        teaching_session_id=session_id,
        created_monotonic_ns=base_ns + 3_050_000_000,
        start_monotonic_ns=base_ns + 3_050_000_000,
        end_monotonic_ns=base_ns + 3_050_000_000,
        text="Use standard shortcut to copy buffer",
        type=AnnotationType.EXPLANATION,
        references={"event_id": "evt_12"},
    )
    teaching_storage.annotation_store.append_annotation(ann1)
    teaching_manifest.transcript_segments = 2
    teaching_manifest.annotations = 1
    teaching_storage.finalize_teaching_session(teaching_manifest)

    return session_storage.session_dir


# ==============================================================================
# 1. Normalization & Canonical Event Model Tests
# ==============================================================================


def test_canonical_event_normalization(temp_dir: Path):
    """Verify raw Phase 2 events map deterministically to canonical models with normalized coords."""
    storage_mgr = StorageManager(temp_dir / "data")
    storage_mgr.initialize_directories()
    session_id = "test_norm_01"
    _create_full_test_session(storage_mgr, session_id)

    builder = RepresentationBuilder(storage_mgr)
    rep_path = builder.build_representation(session_id)
    assert rep_path.exists()

    rep_storage = RepresentationStorage(storage_mgr, session_id)
    events = list(rep_storage.stream_canonical_events())
    assert len(events) == 18

    # Check evt_01: WINDOW_FOCUS_CHANGED -> WINDOW_FOCUS
    evt01 = next(e for e in events if e.source_event_id == "evt_01")
    assert evt01.event_category == EventCategory.WINDOW
    assert evt01.canonical_event_type == CanonicalEventType.WINDOW_FOCUS
    assert evt01.raw_event_type == "window_focus_changed"
    assert evt01.application == "TextEdit"
    assert evt01.window == "Untitled.txt"
    assert evt01.relative_time_ns >= 0
    assert evt01.relative_time_ms >= 0.0

    # Check evt_02: MOUSE_MOVE with normalized coordinates
    evt02 = next(e for e in events if e.source_event_id == "evt_02")
    assert evt02.event_category == EventCategory.POINTER
    assert evt02.canonical_event_type == CanonicalEventType.POINTER_MOVE
    assert evt02.raw_x == 100.0
    assert evt02.raw_y == 100.0
    assert evt02.normalized_x == pytest.approx(100.0 / 1920.0, rel=1e-3)
    assert evt02.normalized_y == pytest.approx(100.0 / 1080.0, rel=1e-3)

    # Check evt_11: KEY_DOWN
    evt11 = next(e for e in events if e.source_event_id == "evt_11")
    assert evt11.event_category == EventCategory.KEYBOARD
    assert evt11.canonical_event_type == CanonicalEventType.KEY_DOWN


# ==============================================================================
# 2. Physical Interaction Derivation Tests
# ==============================================================================


def test_physical_interaction_derivation(temp_dir: Path):
    """Verify physical derivation of clicks, drags, shortcuts, pointer paths, text input and idles."""
    storage_mgr = StorageManager(temp_dir / "data")
    storage_mgr.initialize_directories()
    session_id = "test_deriv_01"
    _create_full_test_session(storage_mgr, session_id)

    rep_storage = RepresentationStorage(storage_mgr, session_id)
    builder = RepresentationBuilder(storage_mgr)
    builder.build_representation(session_id)

    summary = rep_storage.read_summary()
    assert summary is not None

    # Physical Click
    clicks = rep_storage.read_derived_interactions("clicks.json")
    assert len(clicks) >= 1
    click = clicks[0]
    assert click["down_event_id"] == "canon_evt_000005"
    assert click["up_event_id"] == "canon_evt_000006"
    assert click["button"] == "left"
    assert click["raw_x"] == 150.0
    assert click["raw_y"] == 120.0

    # Physical Drag
    drags = rep_storage.read_derived_interactions("drags.json")
    assert len(drags) >= 1
    drag = drags[0]
    assert drag["start_event_id"] == "canon_evt_000007"
    assert drag["end_event_id"] == "canon_evt_000010"
    assert drag["start_position"] == [200.0, 200.0]
    assert drag["end_position"] == [300.0, 300.0]
    assert len(drag["movement_event_ids"]) == 2  # canon_evt_000008, canon_evt_000009

    # Physical Pointer Path
    paths = rep_storage.read_derived_interactions("pointer_paths.json")
    assert len(paths) >= 1
    assert any(p["point_count"] >= 3 for p in paths)

    # Physical Keyboard Shortcut
    shortcuts = rep_storage.read_derived_interactions("shortcuts.json")
    assert len(shortcuts) >= 1
    sc = shortcuts[0]
    assert "ctrl" in sc["modifiers"]
    assert "c" in sc["keys"]
    assert "canon_evt_000011" in sc["event_ids"]
    assert "canon_evt_000012" in sc["event_ids"]

    # Physical Text Input
    text_seqs = rep_storage.read_derived_interactions("text_inputs.json")
    assert len(text_seqs) >= 1
    tseq = text_seqs[0]
    assert tseq["character_count"] == 2
    assert "canon_evt_000015" in tseq["event_ids"]
    assert "canon_evt_000016" in tseq["event_ids"]

    # Physical Idle Interval
    idles = rep_storage.read_derived_interactions("idles.json")
    assert len(idles) >= 1
    idle = idles[0]
    assert idle["duration_ns"] >= 4_000_000_000  # >= 4 seconds


# ==============================================================================
# 3. CRITICAL TEST: Semantic Non-Inference (Section 58)
# ==============================================================================


def test_semantic_non_inference(temp_dir: Path):
    """Verify that Phase 4 does NOT perform semantic UI, intent, or task inference.

    Mouse click at (150, 120) must remain CLICK with position (150, 120), NOT 'OPEN_SETTINGS'.
    CTRL+C must remain physical shortcut, NOT 'COPY_CONTENT'.
    Drag must remain physical drag sequence, NOT 'DRAG_FILE'.
    """
    storage_mgr = StorageManager(temp_dir / "data")
    storage_mgr.initialize_directories()
    session_id = "test_semantic_non_inf"
    _create_full_test_session(storage_mgr, session_id)

    builder = RepresentationBuilder(storage_mgr)
    builder.build_representation(session_id)

    rep_storage = RepresentationStorage(storage_mgr, session_id)

    # 1. Inspect raw JSON of all derived interactions
    clicks = rep_storage.read_derived_interactions("clicks.json")
    click_str = json.dumps(clicks).upper()
    assert "OPEN_SETTINGS" not in click_str
    assert "CLICK_BUTTON" not in click_str
    assert "SELECT_ITEM" not in click_str
    assert clicks[0]["raw_x"] == 150.0

    shortcuts = rep_storage.read_derived_interactions("shortcuts.json")
    sc_str = json.dumps(shortcuts).upper()
    assert "COPY_CONTENT" not in sc_str
    assert "COPY_SELECTION" not in sc_str
    assert "CLIPBOARD_COPY" not in sc_str

    drags = rep_storage.read_derived_interactions("drags.json")
    drag_str = json.dumps(drags).upper()
    assert "DRAG_FILE" not in drag_str
    assert "MOVE_WINDOW" not in drag_str
    assert "REORDER_LIST" not in drag_str

    # 2. Inspect canonical timeline items
    timeline_items = list(rep_storage.stream_timeline_items())
    for item in timeline_items:
        # Item types must be strictly technical
        assert item.item_type in (
            TimelineItemType.EVENT,
            TimelineItemType.FRAME,
            TimelineItemType.WINDOW_CONTEXT,
            TimelineItemType.AUDIO,
            TimelineItemType.SPEECH,
            TimelineItemType.ANNOTATION,
        )


# ==============================================================================
# 4. Unified Canonical Timeline & Deterministic Ordering Tests
# ==============================================================================


def test_unified_canonical_timeline_deterministic_ordering(temp_dir: Path):
    """Verify timeline items are strictly monotonic with deterministic tie-breaking."""
    storage_mgr = StorageManager(temp_dir / "data")
    storage_mgr.initialize_directories()
    session_id = "test_timeline_order"
    _create_full_test_session(storage_mgr, session_id)

    builder = RepresentationBuilder(storage_mgr)
    builder.build_representation(session_id)

    rep_storage = RepresentationStorage(storage_mgr, session_id)
    items = list(rep_storage.stream_timeline_items())
    assert len(items) > 20

    # Ensure strictly sorted order
    prev_time = -1
    for i, it in enumerate(items):
        assert it.monotonic_timestamp_ns >= prev_time
        assert it.relative_time_ns >= 0
        assert it.relative_time_ms >= 0.0
        prev_time = it.monotonic_timestamp_ns

    # Test tie-breaking rule directly on CanonicalTimeline
    t1 = CanonicalTimeline("sess_tie")
    t1.add_item(
        item_type=TimelineItemType.EVENT,
        item_id="evt_b",
        source_id="mouse",
        timestamp_ns=500,
        monotonic_timestamp_ns=500,
        relative_time_ns=0,
        sequence=2,
        priority_rank=1,
    )
    t1.add_item(
        item_type=TimelineItemType.EVENT,
        item_id="evt_a",
        source_id="mouse",
        timestamp_ns=500,
        monotonic_timestamp_ns=500,
        relative_time_ns=0,
        sequence=1,  # sequence 1 before sequence 2 on identical timestamp
        priority_rank=1,
    )
    sorted_items = t1.get_sorted_items()
    assert sorted_items[0].item_id == "evt_a"
    assert sorted_items[1].item_id == "evt_b"


# ==============================================================================
# 5. Deterministic Segmentation & Activity Density Tests
# ==============================================================================


def test_deterministic_segmentation_and_density(temp_dir: Path):
    """Verify demonstration segments are formed at physical boundaries with activity metrics."""
    storage_mgr = StorageManager(temp_dir / "data")
    storage_mgr.initialize_directories()
    session_id = "test_segmentation"
    _create_full_test_session(storage_mgr, session_id)

    builder = RepresentationBuilder(storage_mgr)
    builder.build_representation(session_id)

    rep_storage = RepresentationStorage(storage_mgr, session_id)
    segments = list(rep_storage.stream_segments())
    assert len(segments) >= 2

    # Check segment structure
    seg1 = segments[0]
    assert seg1.segment_id.startswith("seg_")
    assert seg1.duration_ns > 0
    assert seg1.event_count > 0
    assert len(seg1.timeline_item_ids) > 0
    assert seg1.activity_density is not None
    assert seg1.activity_density.events_per_second >= 0.0
    assert seg1.activity_density.idle_ratio >= 0.0
    assert "TextEdit" in seg1.applications or "Terminal" in seg1.applications


# ==============================================================================
# 6. Temporal Relation Graph Tests
# ==============================================================================


def test_temporal_relation_graph(temp_dir: Path):
    """Verify physical and temporal relations (CONTAINS, NEAREST, OVERLAPS) are built deterministically."""
    storage_mgr = StorageManager(temp_dir / "data")
    storage_mgr.initialize_directories()
    session_id = "test_relations"
    _create_full_test_session(storage_mgr, session_id)

    builder = RepresentationBuilder(storage_mgr)
    builder.build_representation(session_id)

    rep_storage = RepresentationStorage(storage_mgr, session_id)
    relations = list(rep_storage.stream_relations())
    assert len(relations) >= 5

    relation_types = {r.relation_type for r in relations}
    assert (
        TemporalRelationType.CONTAINS in relation_types
        or TemporalRelationType.NEAREST in relation_types
    )
    assert TemporalRelationType.NEAREST in relation_types

    # Ensure nearest frame relation points to existing frame
    nearest_frame_rels = [r for r in relations if r.target_id.startswith("frame_")]
    assert len(nearest_frame_rels) > 0
    for r in nearest_frame_rels:
        assert r.relation_type == TemporalRelationType.NEAREST


# ==============================================================================
# 7. Local Compact Indexes & AI Context Window Query Engine
# ==============================================================================


def test_indexes_and_ai_context_window(temp_dir: Path):
    """Verify compact indexes and the high-value AI Context Window Query API."""
    storage_mgr = StorageManager(temp_dir / "data")
    storage_mgr.initialize_directories()
    session_id = "test_ai_context"
    _create_full_test_session(storage_mgr, session_id)

    builder = RepresentationBuilder(storage_mgr)
    builder.build_representation(session_id)

    engine = RepresentationQueryEngine(storage_mgr, session_id)

    # 1. Single Event Lookup
    evt = engine.get_event("evt_05")
    assert evt is not None
    assert evt.source_event_id == "evt_05"
    assert evt.canonical_event_type == CanonicalEventType.POINTER_DOWN

    # 2. Time Range Lookup
    events_in_range = engine.get_events(1_000_000_000, 2_500_000_000)
    assert len(events_in_range) > 0

    # 3. Nearest Frames Lookup
    frame_ref = engine.get_nearest_frames(1_400_000_000)
    assert frame_ref.nearest_frame is not None
    assert frame_ref.nearest_frame.frame_id in ("frame_01", "frame_02")

    # 4. Speech and Annotations Lookup
    speech_items = engine.get_speech(1_000_000_000, 2_000_000_000)
    assert len(speech_items) >= 1
    assert speech_items[0].segment_id == "sp_01"

    # 5. AI Context Window API
    ctx: DemonstrationContext = engine.get_context_window(
        center_timestamp_ns=1_400_000_000,
        before_ns=500_000_000,
        after_ns=500_000_000,
    )
    assert isinstance(ctx, DemonstrationContext)
    assert len(ctx.timeline_items) > 0
    assert len(ctx.events) > 0
    assert ctx.window_context is not None
    assert ctx.window_context.application_name == "TextEdit"
    assert ctx.demonstration_id == session_id

    # Verify context can convert to compact dictionary for AI consumption
    ctx_dict = ctx.to_dict()
    assert "timeline_items" in ctx_dict
    assert "events" in ctx_dict
    assert "nearest_frames" in ctx_dict


# ==============================================================================
# 8. CRITICAL TEST: Raw Evidence Immutability (Section 59)
# ==============================================================================


def test_raw_evidence_immutability(temp_dir: Path):
    """Verify raw Phase 2 & Phase 3 evidence files remain 100% byte-for-byte unchanged after Phase 4."""
    storage_mgr = StorageManager(temp_dir / "data")
    storage_mgr.initialize_directories()
    session_id = "test_raw_immutability"
    _create_full_test_session(storage_mgr, session_id)

    rep_storage = RepresentationStorage(storage_mgr, session_id)

    # 1. Compute pre-build raw evidence hashes
    pre_hashes = rep_storage.compute_raw_evidence_checksums()
    assert len(pre_hashes) >= 4  # manifest, events, frame_index, teaching_manifest, etc.

    # 2. Build canonical representation
    builder = RepresentationBuilder(storage_mgr)
    builder.build_representation(session_id)

    # 3. Compute post-build raw evidence hashes
    post_hashes = rep_storage.compute_raw_evidence_checksums()

    # 4. Verify exact equality
    assert pre_hashes.keys() == post_hashes.keys()
    for rel_path, pre_sha in pre_hashes.items():
        post_sha = post_hashes[rel_path]
        assert pre_sha == post_sha, f"Raw evidence file '{rel_path}' was mutated during Phase 4 build!"


# ==============================================================================
# 9. CRITICAL TEST: Provenance Tracing (Section 60)
# ==============================================================================


def test_provenance_tracing(temp_dir: Path):
    """Verify that every canonical item and derived interaction traces to real raw source IDs."""
    storage_mgr = StorageManager(temp_dir / "data")
    storage_mgr.initialize_directories()
    session_id = "test_provenance"
    _create_full_test_session(storage_mgr, session_id)

    builder = RepresentationBuilder(storage_mgr)
    builder.build_representation(session_id)

    rep_storage = RepresentationStorage(storage_mgr, session_id)

    # 1. Canonical events -> raw source_event_id
    events = list(rep_storage.stream_canonical_events())
    for e in events:
        assert e.source_event_id.startswith("evt_")
        assert e.provenance.recording_session_id == session_id

    # 2. Derived clicks -> valid down & up raw event IDs
    clicks = rep_storage.read_derived_interactions("clicks.json")
    all_event_ids = {e.event_id for e in events}
    for c in clicks:
        assert c["down_event_id"] in all_event_ids
        assert c["up_event_id"] in all_event_ids

    # 3. Derived drags -> valid start, movement, and end raw event IDs
    drags = rep_storage.read_derived_interactions("drags.json")
    for d in drags:
        assert d["start_event_id"] in all_event_ids
        assert d["end_event_id"] in all_event_ids
        for m_id in d["movement_event_ids"]:
            assert m_id in all_event_ids

    # 4. Derived shortcuts -> valid raw keyboard event IDs
    shortcuts = rep_storage.read_derived_interactions("shortcuts.json")
    for sc in shortcuts:
        for eid in sc["event_ids"]:
            assert eid in all_event_ids


# ==============================================================================
# 10. Atomic Build, Validation, Fingerprint & Cache Tests
# ==============================================================================


def test_atomic_build_validation_and_caching(temp_dir: Path):
    """Verify staged atomic build, fingerprint calculation, validation, and caching."""
    storage_mgr = StorageManager(temp_dir / "data")
    storage_mgr.initialize_directories()
    session_id = "test_atomic_cache"
    _create_full_test_session(storage_mgr, session_id)

    builder = RepresentationBuilder(storage_mgr)

    # 1. First build
    rep_path = builder.build_representation(session_id)
    assert rep_path.exists()
    assert (rep_path / "manifest.json").exists()
    assert not (rep_path.parent / "representation.tmp").exists()  # Staging cleaned up

    # 2. Validation report
    report = RepresentationValidator.validate_representation(rep_path, rep_path.parent)
    assert report.is_valid
    assert len(report.errors) == 0

    # 3. Cache check: second build without force uses cache
    manifest_mtime = (rep_path / "manifest.json").stat().st_mtime
    rep_path_cached = builder.build_representation(session_id, force_rebuild=False)
    assert rep_path_cached == rep_path
    assert (rep_path / "manifest.json").stat().st_mtime == manifest_mtime

    # 4. Force rebuild regenerates
    builder.build_representation(session_id, force_rebuild=True)

    # 5. Deterministic fingerprint
    demo = Demonstration.load(session_id, storage_mgr)
    fp1 = demo.manifest.representation_fingerprint
    assert fp1 is not None and len(fp1) == 64

    fp2 = compute_demonstration_fingerprint(
        session_id=session_id,
        schema_version=demo.manifest.schema_version,
        canonical_events=list(RepresentationStorage(storage_mgr, session_id).stream_canonical_events()),
        timeline_items=demo.timeline,
        segments=demo.segments,
        relations=demo.relations,
    )
    assert fp1 == fp2


# ==============================================================================
# 11. Large Session Scalability Benchmark Test (Section 51)
# ==============================================================================


def test_large_session_scalability(temp_dir: Path):
    """Verify building representation on 10,000+ events maintains bounded RAM and fast query times."""
    storage_mgr = StorageManager(temp_dir / "data")
    storage_mgr.initialize_directories()
    session_id = "large_scale_session"

    session_storage = SessionStorage(storage_mgr, session_id)
    session = RecordingSession(session_id=session_id, platform_name="darwin", architecture="arm64")
    session_storage.initialize_session_layout(session.manifest)

    # Stream 10,000 synthetic events
    start_time_ns = 1_000_000_000
    for i in range(10_000):
        t_ns = start_time_ns + i * 5_000_000  # 5ms interval
        session_storage.append_event(
            Event(
                event_id=f"evt_l_{i:06d}",
                session_id=session_id,
                sequence_number=i + 1,
                timestamp="2026-10-04T12:00:00Z",
                monotonic_timestamp=1.0 + (i * 0.005),
                event_type=EventType.MOUSE_MOVE if i % 10 != 0 else EventType.MOUSE_CLICK,
                priority=EventPriority.LOW,
                source="mouse",
                payload={"x": i % 1920, "y": (i * 2) % 1080, "display_id": "disp_0"},
            )
        )

    # Frame index
    frames_meta = {
        "frames": [
            {
                "frame_id": f"frame_l_{j}",
                "monotonic_timestamp": 1.0 + j,
                "timestamp_ns": start_time_ns + j * 1_000_000_000,
                "path": f"frames/frame_l_{j}.webp",
                "checksum": f"chk_{j}",
                "display_id": "disp_0",
                "width": 1920,
                "height": 1080,
            }
            for j in range(50)
        ]
    }
    session_storage.storage_manager.write_metadata(
        session_storage.metadata_dir / "frame_index.json", frames_meta
    )
    for f in frames_meta["frames"]:
        fp = session_storage.session_dir / f["path"]
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_bytes(b"WEBP_TEST")

    session.transition_to(SessionState.RECORDING)
    session.transition_to(SessionState.STOPPING)
    session.transition_to(SessionState.COMPLETED)
    session_storage.finalize_session(
        session.manifest,
        {"events_count": 10_000, "frames_count": 50, "completed_at": "2026-10-04T12:01:00Z"},
        frames_meta,
    )

    # Build representation
    builder = RepresentationBuilder(storage_mgr)
    t0 = time.perf_counter()
    rep_path = builder.build_representation(session_id)
    build_sec = time.perf_counter() - t0

    assert rep_path.exists()
    assert build_sec < 5.0  # Build must be fast (< 5s for 10k events)

    # Validate index query speed on large session
    engine = RepresentationQueryEngine(storage_mgr, session_id)
    t_q0 = time.perf_counter()
    evt = engine.get_event("evt_l_005000")
    q_latency = time.perf_counter() - t_q0

    assert evt is not None
    assert evt.source_event_id == "evt_l_005000"
    assert q_latency < 0.05  # Microsecond to millisecond lookup


# ==============================================================================
# 12. Storage Integrity & Corruption Detection Test
# ==============================================================================


def test_storage_corruption_detection(temp_dir: Path):
    """Verify that any corruption in canonical artifacts is detected by RepresentationValidator."""
    storage_mgr = StorageManager(temp_dir / "data")
    storage_mgr.initialize_directories()
    session_id = "test_corrupt_detect"
    _create_full_test_session(storage_mgr, session_id)

    builder = RepresentationBuilder(storage_mgr)
    rep_path = builder.build_representation(session_id)

    # Clean report first
    clean_report = RepresentationValidator.validate_representation(rep_path, rep_path.parent)
    assert clean_report.is_valid
    assert len(clean_report.errors) == 0

    # Corrupt a single byte in timeline.jsonl
    timeline_file = rep_path / "timeline.jsonl"
    content = timeline_file.read_bytes()
    corrupted_content = content + b"\n{\"corrupt\": true}"
    timeline_file.write_bytes(corrupted_content)

    # Validate must now fail
    corrupt_report = RepresentationValidator.validate_representation(rep_path, rep_path.parent)
    assert not corrupt_report.is_valid
    assert any("Checksum mismatch" in err or "timeline" in err for err in corrupt_report.errors)


# ==============================================================================
# 13. Interrupted / Failed Build Atomic Recovery Test
# ==============================================================================


def test_interrupted_build_atomic_recovery(temp_dir: Path):
    """Verify that interrupted or failing builds do not leave corrupted representation partitions."""
    storage_mgr = StorageManager(temp_dir / "data")
    storage_mgr.initialize_directories()
    session_id = "test_interrupted_build"
    _create_full_test_session(storage_mgr, session_id)

    rep_storage = RepresentationStorage(storage_mgr, session_id)
    builder = RepresentationBuilder(storage_mgr)

    # Simulate an interrupted build leaving a stale staged directory
    stale_temp = rep_storage.create_temp_build_environment()
    (stale_temp / "partial.tmp").write_bytes(b"PARTIAL_BUILD_DATA")
    assert stale_temp.exists()

    # Building cleans up or overwrites staging atomically
    rep_path = builder.build_representation(session_id, force_rebuild=True)
    assert rep_path.exists()
    assert (rep_path / "manifest.json").exists()
    assert not stale_temp.exists()  # Staging was cleaned up / promoted

    report = RepresentationValidator.validate_representation(rep_path, rep_path.parent)
    assert report.is_valid


# ==============================================================================
# 14. Exhaustive Provenance Verification Test
# ==============================================================================


def test_exhaustive_provenance_verification(temp_dir: Path):
    """Verify that every derived canonical object has traceable raw evidence provenance."""
    storage_mgr = StorageManager(temp_dir / "data")
    storage_mgr.initialize_directories()
    session_id = "test_exhaustive_prov"
    _create_full_test_session(storage_mgr, session_id)

    builder = RepresentationBuilder(storage_mgr)
    builder.build_representation(session_id)

    rep_storage = RepresentationStorage(storage_mgr, session_id)

    # 1. Canonical events provenance
    events = list(rep_storage.stream_canonical_events())
    assert len(events) >= 15
    for e in events:
        assert e.source_event_id.startswith("evt_")
        assert e.provenance.recording_session_id == session_id

    all_event_ids = {e.event_id for e in events}

    # 2. Timeline items provenance
    timeline_items = list(rep_storage.stream_timeline_items())
    assert len(timeline_items) >= len(events)
    for t in timeline_items:
        assert t.source_id != ""
        assert t.item_id != ""

    # 3. Text inputs provenance
    text_inputs = rep_storage.read_derived_interactions("text_inputs.json")
    assert len(text_inputs) >= 1
    for ti in text_inputs:
        assert ti["provenance"]["source_session_id"] == session_id
        for eid in ti["event_ids"]:
            assert eid in all_event_ids

    # 4. Window intervals provenance
    win_intervals = rep_storage.read_derived_interactions("window_intervals.json")
    assert len(win_intervals) >= 1
    for wi in win_intervals:
        assert wi["focus_event_id"] in all_event_ids

    # 5. Temporal relations provenance
    relations = list(rep_storage.stream_relations())
    assert len(relations) >= 5
    for r in relations:
        assert r.provenance.get("session_id") == session_id
        assert r.source_id != ""
        assert r.target_id != ""

    # 6. Demonstration segments provenance
    segments = list(rep_storage.stream_segments())
    assert len(segments) >= 1
    all_timeline_ids = {it.item_id for it in timeline_items}
    for seg in segments:
        assert seg.segment_id.startswith("seg_")
        for iid in seg.item_ids:
            assert iid in all_timeline_ids


# ==============================================================================
# 15. Semantic Boundary Invariant Test
# ==============================================================================


def test_semantic_boundary_invariants(temp_dir: Path):
    """Verify that Phase 4 does not perform OCR, intent inference, or autonomous action generation."""
    storage_mgr = StorageManager(temp_dir / "data")
    storage_mgr.initialize_directories()
    session_id = "test_semantic_boundaries"
    _create_full_test_session(storage_mgr, session_id)

    builder = RepresentationBuilder(storage_mgr)
    builder.build_representation(session_id)

    rep_storage = RepresentationStorage(storage_mgr, session_id)

    # 1. No LLM or generative models imported or used in representation package
    import sys
    for mod_name in sys.modules:
        if mod_name.startswith("teach_a_skill.representation"):
            mod = sys.modules[mod_name]
            assert not hasattr(mod, "torch"), f"Unexpected ML dependency torch in {mod_name}"
            assert not hasattr(mod, "transformers"), f"Unexpected ML dependency transformers in {mod_name}"
            assert not hasattr(mod, "langchain"), f"Unexpected ML dependency langchain in {mod_name}"

    # 2. Segments have neutral technical labels, NOT inferred goals or intents
    segments = list(rep_storage.stream_segments())
    for s in segments:
        assert hasattr(s, "boundary_trigger")
        # Ensure no hallucinated or inferred goal / intent fields exist
        d = s.to_dict()
        assert "goal" not in d
        assert "intent" not in d
        assert "predicted_next_action" not in d
        assert "compiled_code" not in d

    # 3. Canonical events contain only physical signals, not semantic actions
    events = list(rep_storage.stream_canonical_events())
    for e in events:
        ed = e.to_dict()
        assert "inferred_intent" not in ed
        assert "ocr_text" not in ed
