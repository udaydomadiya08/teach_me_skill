"""Tests for UniversalRecorder end-to-end lifecycle, state transitions, and replay-as-data."""

import json
from pathlib import Path

from teach_a_skill.recorder.events import Event, EventType
from teach_a_skill.recorder.recorder import UniversalRecorder
from teach_a_skill.recorder.session import SessionState
from teach_a_skill.recorder.sources.os_source import SyntheticScreenEngine


def test_universal_recorder_lifecycle(storage_mgr):
    recorder = UniversalRecorder(
        storage_manager=storage_mgr,
        screen_engine=SyntheticScreenEngine(),
        platform_name="macos",
        architecture="arm64",
    )

    session_id = "test_lifecycle_sess_01"
    recorder.start_recording(
        session_id=session_id,
        use_synthetic_source=True,
        synthetic_event_count=20,
        synthetic_rate_hz=200.0,
    )

    assert recorder.is_recording is True
    assert recorder.is_paused is False
    assert recorder.current_session is not None
    assert recorder.current_session.state == SessionState.RECORDING

    # Ingest some events directly to verify state
    evt = Event.create(
        session_id=session_id,
        sequence_number=999,
        event_type=EventType.MOUSE_CLICK,
        source="mouse",
        payload={"x": 100.0, "y": 200.0, "button": "left"},
    )
    assert recorder.ingest_event(evt) is True

    # Test Pause
    recorder.pause_recording()
    assert recorder.is_paused is True
    assert recorder.is_recording is False
    assert recorder.current_session.state == SessionState.PAUSED

    # Event ingested while paused must be rejected
    assert recorder.ingest_event(evt) is False

    # Test Resume
    recorder.resume_recording()
    assert recorder.is_recording is True
    assert recorder.is_paused is False
    assert recorder.current_session.state == SessionState.RECORDING

    # Test Stop
    session_dir = Path(recorder.stop_recording())
    assert session_dir.exists()
    assert (session_dir / "manifest.json").exists()
    assert (session_dir / "events" / "events.jsonl").exists()
    assert (session_dir / "checksums.json").exists()
    assert (session_dir / "metadata" / "summary.json").exists()

    # Verify manifest status is COMPLETED
    with open(session_dir / "manifest.json", "r", encoding="utf-8") as f:
        manifest_data = json.load(f)
    assert manifest_data["status"] == "COMPLETED"
    assert manifest_data["event_count"] > 0

    # Verify summary is factual non-AI
    with open(session_dir / "metadata" / "summary.json", "r", encoding="utf-8") as f:
        summary_data = json.load(f)
    assert "status" in summary_data
    assert summary_data["status"] == "COMPLETED"
    assert "total_events" in summary_data
    assert "mouse_events" in summary_data
    assert "screenshots_captured" in summary_data


def test_universal_recorder_cancel(storage_mgr):
    recorder = UniversalRecorder(
        storage_manager=storage_mgr,
        screen_engine=SyntheticScreenEngine(),
        platform_name="macos",
        architecture="arm64",
    )

    session_id = "test_cancel_sess_02"
    recorder.start_recording(
        session_id=session_id,
        use_synthetic_source=True,
        synthetic_event_count=10,
        synthetic_rate_hz=200.0,
    )

    session_dir = Path(recorder.cancel_recording())
    assert session_dir.exists()

    with open(session_dir / "manifest.json", "r", encoding="utf-8") as f:
        manifest_data = json.load(f)
    assert manifest_data["status"] == "ABORTED"


def test_universal_recorder_replay_as_data(storage_mgr):
    """Verify stored session provides complete, ordered, synchronized replayable event stream."""
    recorder = UniversalRecorder(
        storage_manager=storage_mgr,
        screen_engine=SyntheticScreenEngine(),
        platform_name="macos",
        architecture="arm64",
    )

    session_id = "test_replay_sess_03"
    recorder.start_recording(
        session_id=session_id,
        use_synthetic_source=True,
        synthetic_event_count=30,
        synthetic_rate_hz=200.0,
    )

    session_dir = Path(recorder.stop_recording())
    events_file = session_dir / "events" / "events.jsonl"

    events = []
    with open(events_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                events.append(json.loads(line))

    assert len(events) >= 2  # At least SESSION_STARTED and SESSION_STOPPED

    # 1. Verify sequence numbers are monotonic
    seqs = [e["sequence_number"] for e in events]
    assert seqs == sorted(seqs)

    # 2. Verify monotonic timestamps are strictly non-decreasing
    mono_times = [e["monotonic_timestamp"] for e in events]
    assert mono_times == sorted(mono_times)

    # 3. Verify screen frames index is synchronized
    frame_index_file = session_dir / "metadata" / "frame_index.json"
    assert frame_index_file.exists()
    with open(frame_index_file, "r", encoding="utf-8") as f:
        frame_idx = json.load(f)

    assert "frames" in frame_idx
    # At least start and stop checkpoints should be indexed
    assert len(frame_idx["frames"]) >= 2
    for frame_entry in frame_idx["frames"]:
        assert "frame_id" in frame_entry
        assert "timestamp" in frame_entry
        assert "monotonic_timestamp" in frame_entry
        assert "trigger_reason" in frame_entry
