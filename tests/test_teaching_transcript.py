"""Tests for Phase 3 Transcript persistence and non-destructive editing."""

from pathlib import Path

from teach_a_skill.teaching.transcript.editor import TranscriptEditor
from teach_a_skill.teaching.transcript.segment import TranscriptSegment
from teach_a_skill.teaching.transcript.store import TranscriptStore


def _create_sample_segment(
    seg_id: str, seq: int, text: str, start_ns: int, end_ns: int
) -> TranscriptSegment:
    return TranscriptSegment(
        segment_id=seg_id,
        teaching_session_id="test_sesh",
        sequence_number=seq,
        start_monotonic_ns=start_ns,
        end_monotonic_ns=end_ns,
        start_wall_time="2026-10-04T12:00:00Z",
        end_wall_time="2026-10-04T12:00:02Z",
        text=text,
        language="en",
        confidence=0.95,
        source="local_stt",
        audio_chunk_ids=[f"chk_{seq}"],
        revision=1,
        is_active=True,
    )


def test_transcript_store_append_and_read(temp_dir: Path):
    """Test appending transcript segments to JSONL and reading them back."""
    trans_file = temp_dir / "transcript.jsonl"
    store = TranscriptStore(trans_file)

    s1 = _create_sample_segment("seg_001", 1, "First I click the button.", 1000, 2000)
    s2 = _create_sample_segment("seg_002", 2, "Then I enter the name.", 2000, 3000)

    store.append_segment(s1)
    store.append_segment(s2)
    store.close()

    segments = store.read_all_segments()
    assert len(segments) == 2
    assert segments[0].segment_id == "seg_001"
    assert segments[0].text == "First I click the button."
    assert segments[1].segment_id == "seg_002"
    assert segments[1].revision == 1


def test_transcript_editor_text_correction(temp_dir: Path):
    """Test text correction increments revision and logs audit trail in corrections.jsonl."""
    trans_file = temp_dir / "transcript.jsonl"
    corr_file = temp_dir / "corrections.jsonl"
    store = TranscriptStore(trans_file, corr_file)

    orig = _create_sample_segment("seg_001", 1, "Click the blue button.", 1000, 2000)
    store.append_segment(orig)
    store.close()

    editor = TranscriptEditor(store)
    updated = editor.edit_segment(
        "seg_001", "Click the blue settings button.", reason="Typo correction"
    )

    assert updated.revision == 2
    assert updated.text == "Click the blue settings button."

    # Verify disk state
    active = store.read_all_segments(only_active=True)
    assert len(active) == 1
    assert active[0].text == "Click the blue settings button."
    assert active[0].revision == 2

    # Verify audit log
    corrections = store.read_all_corrections()
    assert len(corrections) == 1
    assert corrections[0].segment_id == "seg_001"
    assert corrections[0].previous_text == "Click the blue button."
    assert corrections[0].new_text == "Click the blue settings button."
    assert corrections[0].action == "edit"


def test_transcript_editor_split_segment(temp_dir: Path):
    """Test splitting a segment into two contiguous sub-segments."""
    trans_file = temp_dir / "transcript.jsonl"
    store = TranscriptStore(trans_file)

    orig = _create_sample_segment("seg_010", 1, "First sentence. Second sentence.", 1000, 3000)
    store.append_segment(orig)
    store.close()

    editor = TranscriptEditor(store)
    seg1, seg2 = editor.split_segment(
        segment_id="seg_010",
        split_monotonic_ns=2000,
        text_part1="First sentence.",
        text_part2="Second sentence.",
        reason="Separate into two sentences",
    )

    assert seg1.start_monotonic_ns == 1000
    assert seg1.end_monotonic_ns == 2000
    assert seg1.text == "First sentence."

    assert seg2.start_monotonic_ns == 2000
    assert seg2.end_monotonic_ns == 3000
    assert seg2.text == "Second sentence."

    # Active segments on disk should be the 2 children
    active = store.read_all_segments(only_active=True)
    assert len(active) == 2
    assert active[0].segment_id == "seg_010_a"
    assert active[1].segment_id == "seg_010_b"

    # All segments should include the soft-deactivated original
    all_segs = store.read_all_segments(only_active=False)
    assert len(all_segs) == 3
    orig_in_db = next(s for s in all_segs if s.segment_id == "seg_010")
    assert orig_in_db.is_active is False


def test_transcript_editor_merge_segments(temp_dir: Path):
    """Test merging two adjacent segments into one."""
    trans_file = temp_dir / "transcript.jsonl"
    store = TranscriptStore(trans_file)

    s1 = _create_sample_segment("seg_a", 1, "Click here", 1000, 2000)
    s2 = _create_sample_segment("seg_b", 2, "to submit.", 2000, 3000)
    store.append_segment(s1)
    store.append_segment(s2)
    store.close()

    editor = TranscriptEditor(store)
    merged = editor.merge_segments("seg_a", "seg_b", "Click here to submit.")

    assert merged.start_monotonic_ns == 1000
    assert merged.end_monotonic_ns == 3000
    assert merged.text == "Click here to submit."

    active = store.read_all_segments(only_active=True)
    assert len(active) == 1
    assert active[0].text == "Click here to submit."


def test_transcript_editor_soft_hide(temp_dir: Path):
    """Test non-destructive soft-delete of a transcript segment."""
    trans_file = temp_dir / "transcript.jsonl"
    store = TranscriptStore(trans_file)

    s = _create_sample_segment("seg_hide", 1, "Irrelevant chatter.", 1000, 2000)
    store.append_segment(s)
    store.close()

    editor = TranscriptEditor(store)
    editor.hide_segment("seg_hide", reason="Non-task speech")

    active = store.read_all_segments(only_active=True)
    assert len(active) == 0

    all_segs = store.read_all_segments(only_active=False)
    assert len(all_segs) == 1
    assert all_segs[0].is_active is False
