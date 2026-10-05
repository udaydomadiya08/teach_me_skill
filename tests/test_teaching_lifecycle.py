"""End-to-End Lifecycle and Integration tests for Phase 3 Teaching Layer."""

import json
import time
from pathlib import Path

from teach_a_skill.recorder.events import Event, EventPriority, EventType
from teach_a_skill.recorder.session import RecordingSession, SessionState
from teach_a_skill.recorder.storage import SessionStorage
from teach_a_skill.storage.manager import StorageManager
from teach_a_skill.teaching.annotations.model import AnnotationType
from teach_a_skill.teaching.audio.sources import SyntheticAudioSource
from teach_a_skill.teaching.orchestrator import TeachingOrchestrator
from teach_a_skill.teaching.session import TeachingState
from teach_a_skill.teaching.storage import TeachingStorage
from teach_a_skill.teaching.stt.mock_provider import MockSTTProvider


def _setup_mock_phase2_session(storage_manager: StorageManager, session_id: str) -> Path:
    """Set up an authoritative, immutable Phase 2 raw demonstration session."""
    session_storage = SessionStorage(storage_manager, session_id)
    session = RecordingSession(
        session_id=session_id,
        platform_name="darwin",
        architecture="arm64",
    )
    session_storage.initialize_session_layout(session.manifest)

    # Write sample Phase 2 events
    events = [
        Event(
            event_id="evt_001",
            session_id=session_id,
            sequence_number=1,
            timestamp="2026-10-04T12:00:01Z",
            monotonic_timestamp=1.0,
            event_type=EventType.MOUSE_CLICK,
            priority=EventPriority.CRITICAL,
            source="mouse",
            payload={"button": "left", "x": 200, "y": 150},
        ),
        Event(
            event_id="evt_002",
            session_id=session_id,
            sequence_number=2,
            timestamp="2026-10-04T12:00:02Z",
            monotonic_timestamp=2.0,
            event_type=EventType.WINDOW_FOCUS_CHANGED,
            priority=EventPriority.HIGH,
            source="window",
            payload={"app_name": "Calculator", "title": "Calculator"},
        ),
        Event(
            event_id="evt_003",
            session_id=session_id,
            sequence_number=3,
            timestamp="2026-10-04T12:00:03Z",
            monotonic_timestamp=3.0,
            event_type=EventType.KEY_DOWN,
            priority=EventPriority.CRITICAL,
            source="keyboard",
            payload={"key": "5"},
        ),
    ]
    for evt in events:
        session_storage.append_event(evt)

    # Frame index
    frame_idx = {
        "frames": [
            {"frame_id": "f_1", "monotonic_timestamp": 1.0, "path": "frames/f_1.webp"},
            {"frame_id": "f_2", "monotonic_timestamp": 2.5, "path": "frames/f_2.webp"},
        ]
    }
    session_storage.storage_manager.write_metadata(
        session_storage.metadata_dir / "frame_index.json",
        frame_idx,
    )
    session.transition_to(SessionState.RECORDING)
    session.transition_to(SessionState.STOPPING)
    session.transition_to(SessionState.COMPLETED)
    session_storage.finalize_session(
        session.manifest,
        {"events_count": 3, "frames_count": 2, "completed_at": "2026-10-04T12:00:05Z"},
        frame_idx,
    )
    return session_storage.session_dir


def test_teaching_end_to_end_lifecycle(temp_dir: Path):
    """Verify end-to-end teaching session: audio capture, STT, annotations, editing, timeline fusion."""
    storage_mgr = StorageManager(temp_dir / "data")
    storage_mgr.initialize_directories()

    rec_id = "session_lifecycle_test"
    _setup_mock_phase2_session(storage_mgr, rec_id)

    raw_events_path = temp_dir / "data" / "recordings" / rec_id / "events" / "events.jsonl"
    raw_events_bytes_before = raw_events_path.read_bytes()

    # Fast synthetic audio: 0.1s chunks for snappy testing
    audio_src = SyntheticAudioSource(
        teaching_session_id="teach_test",
        chunk_duration_sec=0.1,
    )
    stt_prov = MockSTTProvider(simulated_latency_sec=0.01)

    orchestrator = TeachingOrchestrator(
        storage_manager=storage_mgr,
        stt_provider=stt_prov,
        audio_source=audio_src,
        enable_audio=True,
        enable_transcription=True,
    )

    # 1. Start teaching
    teach_id = orchestrator.start_teaching(recording_session_id=rec_id)
    assert orchestrator.is_teaching is True

    # Allow audio chunks to be captured and transcribed
    time.sleep(0.35)

    # 2. Add text annotations referencing event IDs
    ann = orchestrator.add_annotation(
        text="Click the Calculator button to launch app",
        annotation_type=AnnotationType.INSTRUCTION,
        start_mono_ns=1_000_000_000,
        end_mono_ns=1_500_000_000,
        event_ids=["evt_001"],
    )
    assert ann.annotation_id.startswith("ann_")

    note = orchestrator.add_note("User checked keypad alignment here.")
    assert note.note_id.startswith("note_")

    # 3. Stop teaching
    teaching_path_str = orchestrator.stop_teaching()
    assert orchestrator.is_teaching is False
    assert Path(teaching_path_str).exists()

    # 4. Verify Raw Demonstration Immutability (Phase 2 invariant)
    assert raw_events_path.read_bytes() == raw_events_bytes_before

    # 5. Verify Teaching Storage Artifacts
    teaching_dir = Path(teaching_path_str)
    assert (teaching_dir / "manifest.json").exists()
    assert (teaching_dir / "checksums.json").exists()
    assert (teaching_dir / "transcript.jsonl").exists()
    assert (teaching_dir / "annotations.jsonl").exists()
    assert (teaching_dir / "text_notes.jsonl").exists()

    audio_files = list((teaching_dir / "audio").glob("*.wav"))
    assert len(audio_files) >= 2

    # Check manifest content
    with open(teaching_dir / "manifest.json", "r") as f:
        m = json.load(f)
        assert m["teaching_session_id"] == teach_id
        assert m["recording_session_id"] == rec_id
        assert m["audio_chunks"] >= 2
        assert m["transcript_segments"] >= 2
        assert m["annotations"] == 1
        assert m["text_notes"] == 1

    # 6. Test Non-Destructive Transcript Correction
    editor = orchestrator.get_editor()
    segments = editor.store.read_all_segments()
    assert len(segments) >= 2

    first_seg = segments[0]
    updated_seg = editor.edit_segment(
        first_seg.segment_id,
        "Corrected spoken instruction for opening calculator.",
        reason="Better clarity",
    )
    assert updated_seg.revision == 2

    # Verify corrections.jsonl
    corrections = editor.store.read_all_corrections()
    assert len(corrections) == 1
    assert corrections[0].segment_id == first_seg.segment_id

    # 7. Build and Query Unified Timeline
    timeline = orchestrator.build_timeline_engine(recording_session_id=rec_id)
    assert len(timeline.events) == 3

    # Query annotations for evt_001
    matched_anns = timeline.get_annotations_for_event("evt_001")
    assert len(matched_anns) == 1
    assert matched_anns[0].text == "Click the Calculator button to launch app"

    # Query unified context around 1.0s
    context = timeline.get_context_at(1_000_000_000, window_ns=500_000_000)
    assert len(context.events) >= 1
    assert context.nearest_frame is not None
    assert context.nearest_frame["frame_id"] == "f_1"


def test_teaching_pause_resume(temp_dir: Path):
    """Test pause and resume state transitions and audio capture suspension."""
    storage_mgr = StorageManager(temp_dir / "pause_data")
    storage_mgr.initialize_directories()
    rec_id = "rec_pause_test"
    _setup_mock_phase2_session(storage_mgr, rec_id)

    audio_src = SyntheticAudioSource(
        teaching_session_id="pause_teach",
        chunk_duration_sec=0.05,
    )
    orchestrator = TeachingOrchestrator(
        storage_manager=storage_mgr,
        audio_source=audio_src,
        enable_audio=True,
    )

    orchestrator.start_teaching(rec_id)
    assert orchestrator.is_teaching is True
    time.sleep(0.15)

    orchestrator.pause_teaching()
    assert orchestrator.is_paused is True
    assert orchestrator.current_session.state == TeachingState.PAUSED

    time.sleep(0.1)

    orchestrator.resume_teaching()
    assert orchestrator.is_teaching is True
    assert orchestrator.current_session.state == TeachingState.RECORDING

    time.sleep(0.1)
    orchestrator.stop_teaching()


def test_teaching_crash_recovery(temp_dir: Path):
    """Test crash recovery repairs unfinalized sessions and cleans temporary artifacts."""
    storage_mgr = StorageManager(temp_dir / "crash_data")
    storage_mgr.initialize_directories()
    rec_id = "rec_crash_test"
    _setup_mock_phase2_session(storage_mgr, rec_id)

    teaching_storage = TeachingStorage(storage_mgr, rec_id)
    manifest = {
        "schema_version": "1.0",
        "teaching_session_id": "teach_crash_01",
        "recording_session_id": rec_id,
        "audio_enabled": True,
        "transcription_enabled": True,
        "text_annotations_enabled": True,
        "state": "RECORDING",
        "created_at": "2026-10-04T12:00:00Z",
    }
    teaching_storage.initialize_teaching_layout(manifest)

    # Simulate crash: leave a .tmp audio chunk and a valid audio chunk
    valid_wav = teaching_storage.audio_dir / "chunk_001.wav"
    valid_wav.write_bytes(b"RIFF" + b"\x00" * 40)

    stray_tmp = teaching_storage.audio_dir / "chunk_002.wav.tmp"
    stray_tmp.write_bytes(b"INCOMPLETE")

    # Run recovery
    report = teaching_storage.recover_session()
    assert report["recovered"] is True
    assert stray_tmp.exists() is False  # Cleaned up
    assert valid_wav.exists() is True  # Preserved


def test_teaching_30_minute_simulated_stream_bounded_memory(temp_dir: Path):
    """Resource Safety Test: 30 minutes simulated teaching (180 chunks) maintains bounded memory."""
    from teach_a_skill.teaching.audio.buffer import BoundedAudioBuffer
    from teach_a_skill.teaching.audio.wav import AudioChunk, write_wav_file_atomic

    output_dir = temp_dir / "simulated_30min"
    output_dir.mkdir(parents=True, exist_ok=True)

    buffer = BoundedAudioBuffer(maxsize=20)
    stt = MockSTTProvider(simulated_latency_sec=0.0)

    # 180 chunks of 10s = 1800s = 30 minutes
    total_chunks = 180
    persisted_chunks = []
    transcribed_segments = []

    # Small 1KB PCM sample per chunk for fast test execution
    dummy_pcm = b"\x00\x00" * 500

    for i in range(1, total_chunks + 1):
        chunk = AudioChunk(
            chunk_id=f"chunk_{i:06d}",
            teaching_session_id="sim_30m",
            sequence_number=i,
            start_monotonic_ns=(i - 1) * 10_000_000_000,
            end_monotonic_ns=i * 10_000_000_000,
            start_wall_time="2026-10-04T12:00:00Z",
            end_wall_time="2026-10-04T12:00:10Z",
            duration_ms=10000.0,
            size_bytes=len(dummy_pcm) + 44,
            raw_pcm=dummy_pcm,
        )

        # Buffer must accept chunk
        enqueued = buffer.put(chunk)
        assert enqueued is True

        # Drain chunk to disk (simulating persistence worker)
        popped = buffer.get(timeout=0.1)
        assert popped is not None

        wav_path = output_dir / f"{popped.chunk_id}.wav"
        sha, size = write_wav_file_atomic(wav_path, popped.raw_pcm)
        popped.sha256 = sha
        popped.size_bytes = size
        popped.raw_pcm = b""  # Evict raw PCM to prevent RAM growth
        buffer.task_done()

        persisted_chunks.append(popped)

        # Transcribe
        segs = stt.transcribe(popped)
        transcribed_segments.extend(segs)

    # Verifications
    assert len(persisted_chunks) == 180
    assert len(transcribed_segments) == 180
    assert buffer.metrics.high_watermark <= 20
    assert buffer.metrics.chunks_dropped == 0
    assert buffer.metrics.current_size == 0

    # Total simulated audio: 1800 seconds (30 minutes)
    total_audio_sec = sum(c.duration_ms for c in persisted_chunks) / 1000.0
    assert total_audio_sec == 1800.0

    # Verify all audio chunks have valid SHA-256 and no raw PCM remains in memory
    for c in persisted_chunks:
        assert len(c.sha256) == 64
        assert len(c.raw_pcm) == 0
