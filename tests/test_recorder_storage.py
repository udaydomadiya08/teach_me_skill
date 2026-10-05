"""Tests for SessionStorage, streaming JSONL event storage, checksums, and crash recovery."""

import pytest

from teach_a_skill.core.errors import StorageError
from teach_a_skill.recorder.events import Event, EventType
from teach_a_skill.recorder.screen import ScreenFrame
from teach_a_skill.recorder.session import RecordingSession, SessionState
from teach_a_skill.recorder.storage import SessionStorage


def _create_test_session(session_id: str = "test_sess_01") -> RecordingSession:
    session = RecordingSession(
        session_id=session_id,
        platform_name="macos",
        architecture="arm64",
    )
    session.transition_to(SessionState.RECORDING)
    return session


def test_session_storage_layout_and_append(storage_mgr):
    session = _create_test_session("test_sess_layout")
    storage = SessionStorage(storage_mgr, session.session_id)
    storage.initialize_session_layout(session.manifest)

    assert storage.events_dir.exists()
    assert storage.frames_dir.exists()
    assert storage.metadata_dir.exists()
    assert storage.manifest_file.exists()

    # Append events
    e1 = Event.create(
        session_id=session.session_id,
        sequence_number=1,
        event_type=EventType.SESSION_STARTED,
        source="system",
        payload={"tier": "BALANCED"},
    )
    e2 = Event.create(
        session_id=session.session_id,
        sequence_number=2,
        event_type=EventType.MOUSE_CLICK,
        source="mouse",
        payload={"x": 200.0, "y": 300.0, "button": "left"},
    )

    storage.append_event(e1)
    storage.append_event(e2)

    # Read back events
    events = storage.read_all_events()
    assert len(events) == 2
    assert events[0].event_type == EventType.SESSION_STARTED
    assert events[1].event_type == EventType.MOUSE_CLICK
    assert events[1].payload["x"] == 200.0

    storage.close()


def test_session_storage_save_frame_and_finalize(storage_mgr):
    session = _create_test_session("test_sess_finalize")
    storage = SessionStorage(storage_mgr, session.session_id)
    storage.initialize_session_layout(session.manifest)

    # Create dummy PNG frame
    frame = ScreenFrame(
        frame_id="frame_001",
        timestamp="2026-10-04T12:00:00Z",
        monotonic_timestamp=100.0,
        display_id=0,
        width=100,
        height=100,
        scale_factor=1.0,
        trigger_reason="mouse_click",
        triggering_event_id="evt_01",
        image_bytes=b"\x89PNG\r\n\x1a\nfakeimagebytes",
    )
    frame_path = storage.save_frame(frame)
    assert frame_path.exists()
    assert frame_path.read_bytes() == b"\x89PNG\r\n\x1a\nfakeimagebytes"

    # Finalize
    manifest = session.manifest
    manifest.event_count = 5
    checksums = storage.finalize_session(
        manifest=manifest,
        summary={"duration": 10.0, "total_events": 5},
        frame_index={"frame_001": {"timestamp": 100.0}},
    )

    assert "manifest.json" in checksums
    assert "events.jsonl" in checksums
    assert storage.checksums_file.exists()
    assert (storage.metadata_dir / "summary.json").exists()
    assert (storage.metadata_dir / "frame_index.json").exists()


def test_crash_recovery_aborted_session(storage_mgr):
    session = _create_test_session("test_sess_crash")
    storage = SessionStorage(storage_mgr, session.session_id)
    storage.initialize_session_layout(session.manifest)

    # Write events simulating unexpected crash while RECORDING (no SESSION_STOPPED event)
    for i in range(1, 4):
        storage.append_event(
            Event.create(
                session_id=session.session_id,
                sequence_number=i,
                event_type=EventType.MOUSE_MOVE,
                source="mouse",
                payload={"x": float(i * 10), "y": 50.0},
            )
        )
    storage.close()

    # Recover the crashed session
    recovered_manifest = SessionStorage.recover_session(storage_mgr, session.session_id)
    assert recovered_manifest.status == SessionState.ABORTED
    assert recovered_manifest.event_count == 3
    assert recovered_manifest.event_counts_by_type.get("MOUSE_MOVE") == 3

    # Calling recover again on already aborted session returns without error
    manifest2 = SessionStorage.recover_session(storage_mgr, session.session_id)
    assert manifest2.status == SessionState.ABORTED


def test_crash_recovery_completed_session_with_stop_event(storage_mgr):
    session = _create_test_session("test_sess_clean_stop")
    storage = SessionStorage(storage_mgr, session.session_id)
    storage.initialize_session_layout(session.manifest)

    storage.append_event(
        Event.create(
            session_id=session.session_id,
            sequence_number=1,
            event_type=EventType.SESSION_STOPPED,
            source="system",
            payload={},
        )
    )
    storage.close()

    recovered_manifest = SessionStorage.recover_session(storage_mgr, session.session_id)
    assert recovered_manifest.status == SessionState.COMPLETED
    assert recovered_manifest.event_count == 1


def test_crash_recovery_missing_manifest_raises(storage_mgr):
    with pytest.raises(StorageError):
        SessionStorage.recover_session(storage_mgr, "non_existent_session_id")
