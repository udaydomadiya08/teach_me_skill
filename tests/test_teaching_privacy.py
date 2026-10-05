"""Privacy and Network Isolation tests for Phase 3 Teaching Layer."""

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from teach_a_skill.core.errors import PrivacyViolationError
from teach_a_skill.privacy.guard import PrivacyGuard
from teach_a_skill.privacy.policy import PrivacyPolicy
from teach_a_skill.recorder.session import RecordingSession, SessionState
from teach_a_skill.recorder.storage import SessionStorage
from teach_a_skill.storage.manager import StorageManager
from teach_a_skill.teaching.annotations.model import AnnotationType
from teach_a_skill.teaching.audio.sources import SyntheticAudioSource
from teach_a_skill.teaching.orchestrator import TeachingOrchestrator
from teach_a_skill.teaching.stt.mock_provider import MockSTTProvider


def _setup_session(storage_manager: StorageManager, session_id: str) -> None:
    session_storage = SessionStorage(storage_manager, session_id)
    session = RecordingSession(session_id=session_id, platform_name="darwin", architecture="arm64")
    session_storage.initialize_session_layout(session.manifest)
    session.transition_to(SessionState.RECORDING)
    session.transition_to(SessionState.STOPPING)
    session.transition_to(SessionState.COMPLETED)
    session_storage.finalize_session(
        session.manifest,
        {"events_count": 0, "frames_count": 0},
        {"frames": []},
    )


def test_zero_network_access_guarantee(temp_dir: Path):
    """Test that all Phase 3 operations execute with 100% offline isolation and zero socket calls."""
    storage_mgr = StorageManager(temp_dir / "offline_data")
    storage_mgr.initialize_directories()
    rec_id = "rec_offline_01"
    _setup_session(storage_mgr, rec_id)

    # Poison socket creation to guarantee failure if any network call occurs
    def poison_socket(*args, **kwargs):
        raise RuntimeError("NETWORK ACCESS FORBIDDEN in local-only Phase 3 teaching layer!")

    with (
        patch("socket.socket", side_effect=poison_socket),
        patch("socket.create_connection", side_effect=poison_socket),
    ):
        audio_src = SyntheticAudioSource(
            teaching_session_id="offline_teach",
            chunk_duration_sec=0.05,
        )
        stt_prov = MockSTTProvider(simulated_latency_sec=0.005)

        orchestrator = TeachingOrchestrator(
            storage_manager=storage_mgr,
            stt_provider=stt_prov,
            audio_source=audio_src,
            enable_audio=True,
            enable_transcription=True,
        )

        _ = orchestrator.start_teaching(recording_session_id=rec_id)
        time.sleep(0.15)

        # Annotate
        orchestrator.add_annotation(
            text="Completely offline instruction",
            annotation_type=AnnotationType.INSTRUCTION,
        )
        orchestrator.add_note("Offline note")

        # Stop
        path_str = orchestrator.stop_teaching()
        assert Path(path_str).exists()

        # Build timeline
        timeline = orchestrator.build_timeline_engine(rec_id)
        ctx = timeline.get_context_at(1_000_000_000)
        assert ctx is not None


def test_privacy_guard_blocks_microphone(temp_dir: Path):
    """Test PrivacyGuard blocks microphone access when privacy policy forbids audio."""
    storage_mgr = StorageManager(temp_dir / "priv_data")
    storage_mgr.initialize_directories()
    rec_id = "rec_priv_01"
    _setup_session(storage_mgr, rec_id)

    # Create policy with audio disallowed (_microphone_allowed=False by default)
    policy = PrivacyPolicy(_microphone_allowed=False)
    guard = PrivacyGuard(policy)

    orchestrator = TeachingOrchestrator(
        storage_manager=storage_mgr,
        privacy_guard=guard,
        enable_audio=True,
    )

    with pytest.raises(PrivacyViolationError):
        orchestrator.start_teaching(recording_session_id=rec_id)
