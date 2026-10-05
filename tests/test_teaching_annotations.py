"""Tests for Phase 3 Teaching Annotations and Text Notes Subsystem."""

from pathlib import Path

from teach_a_skill.teaching.annotations.model import AnnotationType, TeachingAnnotation, TextNote
from teach_a_skill.teaching.annotations.store import TeachingAnnotationStore


def test_teaching_annotation_serialization():
    """Test TeachingAnnotation data structure and serialization."""
    ann = TeachingAnnotation(
        annotation_id="ann_001",
        teaching_session_id="test_session",
        created_monotonic_ns=1000,
        start_monotonic_ns=1000,
        end_monotonic_ns=2000,
        text="Click the save icon to persist changes.",
        type=AnnotationType.INSTRUCTION,
        author="user",
        revision=1,
        references={"event_ids": ["evt_104", "evt_105"]},
    )
    d = ann.to_dict()
    assert d["type"] == "instruction"
    assert d["references"]["event_ids"] == ["evt_104", "evt_105"]

    json_str = ann.to_json()
    assert "Click the save icon" in json_str

    deserialized = TeachingAnnotation.from_dict(d)
    assert deserialized.annotation_id == ann.annotation_id
    assert deserialized.type == AnnotationType.INSTRUCTION
    assert deserialized.references == ann.references


def test_text_note_serialization():
    """Test TextNote data structure and serialization."""
    note = TextNote(
        note_id="note_001",
        teaching_session_id="test_session",
        timestamp_monotonic_ns=5000,
        wall_time="2026-10-04T12:00:00Z",
        text="Quick reminder: check credentials first.",
    )
    d = note.to_dict()
    assert d["note_id"] == "note_001"
    assert d["text"] == "Quick reminder: check credentials first."

    deserialized = TextNote.from_dict(d)
    assert deserialized.note_id == note.note_id
    assert deserialized.timestamp_monotonic_ns == note.timestamp_monotonic_ns


def test_annotation_store_persistence(temp_dir: Path):
    """Test storing and reading annotations and text notes on disk."""
    ann_file = temp_dir / "annotations.jsonl"
    note_file = temp_dir / "text_notes.jsonl"
    store = TeachingAnnotationStore(ann_file, note_file)

    a1 = TeachingAnnotation(
        annotation_id="ann_01",
        teaching_session_id="s1",
        created_monotonic_ns=100,
        start_monotonic_ns=100,
        end_monotonic_ns=200,
        text="Important instruction",
        type=AnnotationType.INSTRUCTION,
        references={"event_ids": ["evt_1"]},
    )
    a2 = TeachingAnnotation(
        annotation_id="ann_02",
        teaching_session_id="s1",
        created_monotonic_ns=300,
        start_monotonic_ns=300,
        end_monotonic_ns=400,
        text="Warning: do not press delete",
        type=AnnotationType.WARNING,
        is_active=False,
    )
    store.append_annotation(a1)
    store.append_annotation(a2)

    n1 = TextNote(
        note_id="note_01",
        teaching_session_id="s1",
        timestamp_monotonic_ns=50,
        wall_time="2026-10-04T12:00:00Z",
        text="A note during demonstration",
    )
    store.append_note(n1)
    store.close()

    active_anns = store.read_all_annotations(only_active=True)
    assert len(active_anns) == 1
    assert active_anns[0].annotation_id == "ann_01"

    all_anns = store.read_all_annotations(only_active=False)
    assert len(all_anns) == 2

    notes = store.read_all_notes()
    assert len(notes) == 1
    assert notes[0].note_id == "note_01"


def test_annotation_store_rewrite_for_updates(temp_dir: Path):
    """Test atomically rewriting annotations for revisioning."""
    ann_file = temp_dir / "annotations.jsonl"
    store = TeachingAnnotationStore(ann_file)

    a1 = TeachingAnnotation(
        annotation_id="ann_01",
        teaching_session_id="s1",
        created_monotonic_ns=100,
        start_monotonic_ns=100,
        end_monotonic_ns=200,
        text="Original text",
        type=AnnotationType.NOTE,
    )
    store.append_annotation(a1)

    # Edit
    all_anns = store.read_all_annotations(only_active=False)
    all_anns[0].text = "Updated text"
    all_anns[0].revision = 2
    store.rewrite_annotations(all_anns)

    updated = store.read_all_annotations()
    assert len(updated) == 1
    assert updated[0].text == "Updated text"
    assert updated[0].revision == 2
