"""Tests for recording session state machine and manifest."""

import pytest

from teach_a_skill.recorder.session import (
    RecordingSession,
    SessionManifest,
    SessionState,
    SessionStateError,
)


def test_session_state_machine_valid_transitions():
    session = RecordingSession(
        session_id="test_sess_01",
        platform_name="macos",
        architecture="arm64",
    )
    assert session.state == SessionState.CREATED

    # CREATED -> RECORDING
    session.transition_to(SessionState.RECORDING)
    assert session.state == SessionState.RECORDING
    assert session.manifest.started_at is not None

    # RECORDING -> PAUSED
    session.transition_to(SessionState.PAUSED)
    assert session.state == SessionState.PAUSED

    # PAUSED -> RECORDING
    session.transition_to(SessionState.RECORDING)
    assert session.state == SessionState.RECORDING

    # RECORDING -> STOPPING -> COMPLETED
    session.transition_to(SessionState.STOPPING)
    assert session.state == SessionState.STOPPING

    session.transition_to(SessionState.COMPLETED)
    assert session.state == SessionState.COMPLETED
    assert session.manifest.ended_at is not None
    assert session.manifest.duration_sec >= 0.0


def test_session_state_machine_invalid_transitions():
    session = RecordingSession(
        session_id="test_sess_02",
        platform_name="linux",
        architecture="x86_64",
    )
    # Cannot jump directly from CREATED to COMPLETED
    with pytest.raises(SessionStateError, match="Invalid state transition"):
        session.transition_to(SessionState.COMPLETED)

    # Transition to RECORDING
    session.transition_to(SessionState.RECORDING)

    # Transition to STOPPING
    session.transition_to(SessionState.STOPPING)

    # Cannot transition back to RECORDING from STOPPING
    with pytest.raises(SessionStateError, match="Invalid state transition"):
        session.transition_to(SessionState.RECORDING)

    session.transition_to(SessionState.COMPLETED)

    # Terminal state cannot transition to anything
    with pytest.raises(SessionStateError, match="Invalid state transition"):
        session.transition_to(SessionState.RECORDING)


def test_session_state_aborted():
    session = RecordingSession(
        session_id="test_sess_abort",
        platform_name="windows",
        architecture="x86_64",
    )
    session.transition_to(SessionState.RECORDING)
    session.transition_to(SessionState.ABORTED)
    assert session.state == SessionState.ABORTED


def test_session_manifest_serialization():
    session = RecordingSession(
        session_id="test_sess_manifest",
        platform_name="macos",
        architecture="arm64",
        hardware_profile={"tier": "BASELINE"},
    )
    session.transition_to(SessionState.RECORDING)
    session.record_event_metric("MOUSE_CLICK", app_name="Finder")
    session.record_event_metric("KEY_DOWN", app_name="Finder")
    session.record_frame_metric("frame_0001", "mouse_click")
    session.transition_to(SessionState.STOPPING)
    session.transition_to(SessionState.COMPLETED)

    m_dict = session.manifest.to_dict()
    assert m_dict["session_id"] == "test_sess_manifest"
    assert m_dict["status"] == "COMPLETED"
    assert m_dict["event_count"] == 2
    assert "Finder" in m_dict["distinct_applications"]

    hydrated = SessionManifest.from_dict(m_dict)
    assert hydrated.session_id == session.manifest.session_id
    assert hydrated.status == SessionState.COMPLETED
    assert hydrated.event_count == 2
