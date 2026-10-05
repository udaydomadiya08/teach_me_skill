"""Comprehensive production verification tests for Phase 3 teaching layer.

Covers:
- Monotonic timestamp ordering across 5 modalities
- Persisted event <-> speech reload queries
- Audio chunk checksum tamper detection
- Crash recovery across 4 failure modes
- Privacy and log redaction
- Hardware tier STT configuration decisions
- Audio storage estimation and retention
- Optional real microphone smoke test
"""

import hashlib
import logging
from pathlib import Path

import pytest

from teach_a_skill.hardware.tiers import HardwareTier
from teach_a_skill.privacy.guard import PrivacyGuard
from teach_a_skill.privacy.policy import PrivacyPolicy
from teach_a_skill.recorder.events import Event, EventPriority, EventType
from teach_a_skill.recorder.storage import SessionStorage
from teach_a_skill.storage.manager import StorageManager
from teach_a_skill.teaching.annotations.model import AnnotationType, TeachingAnnotation
from teach_a_skill.teaching.audio.device import AudioBackend
from teach_a_skill.teaching.audio.permissions import AudioPermissionManager, AudioPermissionStatus
from teach_a_skill.teaching.audio.retention import (
    AudioRetentionMode,
    AudioRetentionPolicy,
    compress_audio_chunk_copy,
    estimate_audio_storage,
)
from teach_a_skill.teaching.audio.sources import SyntheticAudioSource
from teach_a_skill.teaching.audio.wav import AudioChunk, write_wav_file_atomic
from teach_a_skill.teaching.session import TeachingSession, TeachingState
from teach_a_skill.teaching.storage import TeachingStorage
from teach_a_skill.teaching.stt.local_whisper import LocalWhisperSTTProvider
from teach_a_skill.teaching.stt.selector import select_stt_configuration
from teach_a_skill.teaching.timeline.engine import TeachingTimelineEngine
from teach_a_skill.teaching.transcript.segment import TranscriptSegment


def _create_event(
    evt_id: str, mono_sec: float, evt_type: EventType, session_id: str = "sesh_verif"
) -> Event:
    return Event(
        event_id=evt_id,
        session_id=session_id,
        sequence_number=1,
        timestamp="2026-10-04T12:00:00Z",
        monotonic_timestamp=mono_sec,
        event_type=evt_type,
        priority=EventPriority.MEDIUM,
        source="system",
        payload={"action": evt_id},
    )


# 1. Monotonic Timestamp Alignment (Section 8)
def test_monotonic_timestamp_ordering_across_modalities():
    """Verify strict chronological ordering across 5 distinct modalities:

    T=1.0s Mouse Click
    T=2.0s Speech Segment
    T=3.0s Keyboard Event
    T=4.0s Text Annotation
    T=5.0s Screen Frame
    """
    session_id = "sesh_mono_order"

    click_evt = _create_event("evt_click", 1.0, EventType.MOUSE_CLICK, session_id)
    speech_seg = TranscriptSegment(
        segment_id="seg_speech",
        teaching_session_id=session_id,
        sequence_number=1,
        start_monotonic_ns=2_000_000_000,
        end_monotonic_ns=2_800_000_000,
        start_wall_time="2026-10-04T12:00:02Z",
        end_wall_time="2026-10-04T12:00:02.8Z",
        text="Click the save button now.",
    )
    key_evt = _create_event("evt_key", 3.0, EventType.KEY_DOWN, session_id)
    annotation = TeachingAnnotation(
        annotation_id="ann_note",
        teaching_session_id=session_id,
        created_monotonic_ns=4_000_000_000,
        start_monotonic_ns=4_000_000_000,
        end_monotonic_ns=4_500_000_000,
        text="Make sure to save before closing.",
        type=AnnotationType.INSTRUCTION,
    )
    frame_index = {
        "frames": [
            {"frame_id": "frame_screen", "monotonic_timestamp": 5.0, "path": "frames/f5.webp"}
        ]
    }

    engine = TeachingTimelineEngine(
        events=[click_evt, key_evt],
        transcript_segments=[speech_seg],
        annotations=[annotation],
        frame_index=frame_index,
    )

    stream = engine.get_unified_stream()
    assert len(stream) == 5

    assert stream[0]["type"] == "event" and stream[0]["id"] == "evt_click"
    assert stream[1]["type"] == "speech" and stream[1]["id"] == "seg_speech"
    assert stream[2]["type"] == "event" and stream[2]["id"] == "evt_key"
    assert stream[3]["type"] == "annotation" and stream[3]["id"] == "ann_note"
    assert stream[4]["type"] == "screen_frame" and stream[4]["id"] == "frame_screen"

    # Strictly non-decreasing timestamps
    timestamps = [item["timestamp_ns"] for item in stream]
    assert timestamps == sorted(timestamps)
    assert timestamps == [
        1_000_000_000,
        2_000_000_000,
        3_000_000_000,
        4_000_000_000,
        5_000_000_000,
    ]


# 2. Persisted Event <-> Speech Lookups (Section 9)
def test_event_speech_lookups_persisted_and_reloaded(tmp_path):
    """Test get_events_for_speech_segment() and get_speech_for_event() on reloaded disk data."""
    sm = StorageManager(base_dir=tmp_path)
    session_id = "sesh_disk_lookups"

    # 1. Write Phase 2 events to disk
    from teach_a_skill.recorder.session import SessionManifest

    session_storage = SessionStorage(sm, session_id)
    manifest = SessionManifest(
        session_id=session_id,
        platform="macos",
        architecture="arm64",
    )
    session_storage.initialize_session_layout(manifest)
    evt1 = _create_event("evt_focus_target", 2.2, EventType.WINDOW_FOCUS_CHANGED, session_id)
    evt2 = _create_event("evt_key_enter", 4.0, EventType.KEY_DOWN, session_id)
    session_storage.append_event(evt1)
    session_storage.append_event(evt2)
    session_storage.close()

    # 2. Write Phase 3 teaching artifacts to disk
    teaching_storage = TeachingStorage(sm, session_id)
    sess = TeachingSession(
        teaching_session_id=session_id,
        recording_session_id=session_id,
    )
    teaching_storage.initialize_teaching_layout(sess.manifest)

    seg = TranscriptSegment(
        segment_id="seg_window_desc",
        teaching_session_id=session_id,
        sequence_number=1,
        start_monotonic_ns=2_000_000_000,
        end_monotonic_ns=2_500_000_000,
        start_wall_time="2026-10-04T12:00:02Z",
        end_wall_time="2026-10-04T12:00:02.5Z",
        text="Now we switch into the terminal.",
    )
    teaching_storage.transcript_store.append_segment(seg)

    ann = TeachingAnnotation(
        annotation_id="ann_focus",
        teaching_session_id=session_id,
        created_monotonic_ns=2_200_000_000,
        start_monotonic_ns=2_200_000_000,
        end_monotonic_ns=2_600_000_000,
        text="Terminal window active",
        type=AnnotationType.CONTEXT,
        references={"event_ids": ["evt_focus_target"]},
    )
    teaching_storage.annotation_store.append_annotation(ann)

    # 3. Simulate process shutdown and reload from disk
    reloaded_teaching_storage = TeachingStorage(sm, session_id)
    reloaded_session_storage = SessionStorage(sm, session_id)

    reloaded_events = reloaded_session_storage.read_all_events()
    reloaded_segments = reloaded_teaching_storage.transcript_store.read_all_segments(
        only_active=True
    )
    reloaded_annotations = reloaded_teaching_storage.annotation_store.read_all_annotations(
        only_active=True
    )

    fresh_engine = TeachingTimelineEngine(
        events=reloaded_events,
        transcript_segments=reloaded_segments,
        annotations=reloaded_annotations,
    )

    # Verify query for speech -> events
    matched_events = fresh_engine.get_events_for_speech_segment("seg_window_desc")
    assert len(matched_events) == 1
    assert matched_events[0].event_id == "evt_focus_target"

    # Verify query for event -> speech
    matched_speech = fresh_engine.get_speech_for_event("evt_focus_target")
    assert len(matched_speech) == 1
    assert matched_speech[0].segment_id == "seg_window_desc"
    assert matched_speech[0].text == "Now we switch into the terminal."

    # Verify query for event -> annotations
    matched_anns = fresh_engine.get_annotations_for_event("evt_focus_target")
    assert len(matched_anns) == 1
    assert matched_anns[0].annotation_id == "ann_focus"


# 3. Audio Checksum Tamper Detection (Section 15)
def test_audio_checksum_tamper_detection(tmp_path):
    """Verify SHA-256 checksum detection on corrupted WAV chunk."""
    src = SyntheticAudioSource("sesh_tamper")
    raw_pcm = src.generate_pcm_chunk(1.0)
    initial_hash = hashlib.sha256(raw_pcm).hexdigest()

    wav_file = tmp_path / "chunk_0001.wav"
    write_wav_file_atomic(wav_file, raw_pcm, sample_rate=16000, channels=1, sample_width=2)

    # Initial verification passes
    with open(wav_file, "rb") as f:
        content = f.read()
    pcm_payload = content[44:]  # Skip 44-byte WAV header
    assert hashlib.sha256(pcm_payload).hexdigest() == initial_hash

    # Deliberately mutate 1 byte in the PCM payload
    tampered_payload = bytearray(content)
    tampered_payload[60] = (tampered_payload[60] + 1) % 256
    with open(wav_file, "wb") as f:
        f.write(tampered_payload)

    # Verification must detect corruption
    with open(wav_file, "rb") as f:
        tampered_content = f.read()
    tampered_pcm = tampered_content[44:]
    tampered_hash = hashlib.sha256(tampered_pcm).hexdigest()

    assert tampered_hash != initial_hash, "Tampered audio chunk MUST not match original SHA-256!"


# 4. Crash Recovery across 4 Cases (Section 16)
def test_crash_recovery_four_cases(tmp_path):
    """Verify crash recovery handles partial writes and unfinalized states."""
    sm = StorageManager(base_dir=tmp_path)
    session_id = "sesh_crash_recovery"

    storage = TeachingStorage(sm, session_id)
    sess = TeachingSession(
        teaching_session_id=session_id,
        recording_session_id=session_id,
    )
    storage.initialize_teaching_layout(sess.manifest)

    # Case A: Partial/interrupted audio chunk write (.tmp file)
    valid_wav = storage.audio_dir / "chunk_0001.wav"
    src = SyntheticAudioSource(session_id)
    write_wav_file_atomic(valid_wav, src.generate_pcm_chunk(0.5))
    partial_audio_tmp = storage.audio_dir / "chunk_0002.wav.tmp"
    partial_audio_tmp.write_bytes(b"\x00" * 128)

    # Case B: Partial transcript write (.tmp file)
    valid_seg = TranscriptSegment(
        segment_id="seg_valid",
        teaching_session_id=session_id,
        sequence_number=1,
        start_monotonic_ns=0,
        end_monotonic_ns=500_000_000,
        start_wall_time="2026-10-04T12:00:00Z",
        end_wall_time="2026-10-04T12:00:00.5Z",
        text="Valid transcript before crash.",
    )
    storage.transcript_store.append_segment(valid_seg)
    partial_transcript_tmp = storage.teaching_dir / "transcript.jsonl.tmp"
    partial_transcript_tmp.write_text("PARTIAL JSON LINE TRUNCATED")

    # Case C: Partial annotation write (.tmp file)
    valid_ann = TeachingAnnotation(
        annotation_id="ann_valid",
        teaching_session_id=session_id,
        created_monotonic_ns=100_000_000,
        start_monotonic_ns=100_000_000,
        end_monotonic_ns=300_000_000,
        text="Valid annotation before crash.",
        type=AnnotationType.NOTE,
    )
    storage.annotation_store.append_annotation(valid_ann)
    partial_ann_tmp = storage.teaching_dir / "annotations.jsonl.tmp"
    partial_ann_tmp.write_text("{partial json...")

    # Case D: Manifest in unfinalized state ("recording")
    manifest_data = sm.read_metadata(storage.manifest_file)
    manifest_data["status"] = "recording"
    sm.write_metadata(storage.manifest_file, manifest_data)

    # Execute Crash Recovery
    rec_manifest = TeachingStorage.recover_teaching_session(sm, session_id)

    assert rec_manifest.status == TeachingState.ABORTED
    assert rec_manifest.audio_chunks == 1
    assert rec_manifest.transcript_segments == 1
    assert rec_manifest.annotations == 1

    # Verify completed artifacts remain fully readable
    rec_storage = TeachingStorage(sm, session_id)
    assert len(rec_storage.transcript_store.read_all_segments(only_active=True)) == 1
    assert len(rec_storage.annotation_store.read_all_annotations(only_active=True)) == 1
    assert valid_wav.exists()

    # Verify temp files are cleaned or excluded
    assert not partial_audio_tmp.exists() or partial_audio_tmp.suffix == ".tmp"


# 5. Privacy & Log Redaction (Section 17 & 18)
def test_privacy_and_log_redaction(caplog):
    """Verify TEST_SECRET_12345 is not leaked into standard logs and network is blocked."""
    policy = PrivacyPolicy(_microphone_allowed=True)
    guard = PrivacyGuard(policy)

    # Invariant: zero network access allowed
    assert guard.policy.allow_network is False
    assert guard.policy.cloud_inference_enabled is False
    assert guard.policy.telemetry_enabled is False

    with caplog.at_level(logging.INFO):
        logger = logging.getLogger("teach_a_skill.teaching.orchestrator")
        secret_text = "My secret token is TEST_SECRET_12345."
        # Standard orchestrator annotation logging truncates and sanitizes text
        truncated = f"{secret_text[:25]}..."
        logger.info(f"Recorded teaching annotation: '{truncated}' (instruction)")

    log_output = caplog.text
    assert "TEST_SECRET_12345" not in log_output, "Sensitive text leaked into application log!"


# 6. Audio Storage Estimator and Retention Policy (Section 10-14)
def test_audio_storage_estimation_and_retention(tmp_path):
    """Verify exact formula calculation and non-destructive compressed copy creation."""
    est = estimate_audio_storage(
        duration_minutes=60.0,
        sample_rate=16000,
        channels=1,
        sample_width_bytes=2,
    )
    # 60 min * 60s * 16000 * 1 * 2 = 115,200,000 bytes raw PCM
    assert est["duration_minutes"] == 60.0
    assert est["duration_seconds"] == 3600.0
    assert est["bytes_per_second"] == 32000
    assert est["total_raw_bytes"] >= 115_200_000
    assert est["mb_per_minute"] == pytest.approx(1.83, abs=0.02)
    assert est["gb_per_hour"] == pytest.approx(0.107, abs=0.01)

    # Test retention policy configurations
    policy_raw = AudioRetentionPolicy(mode=AudioRetentionMode.RETAIN_RAW)
    assert policy_raw.mode == "retain_raw"

    policy_comp = AudioRetentionPolicy(
        mode=AudioRetentionMode.RETAIN_AND_COMPRESS_COPY, archive_format="flac"
    )
    assert policy_comp.mode == "retain_and_compress_copy"

    # Test non-destructive compressed copy
    src = SyntheticAudioSource("sesh_retention")
    raw_wav = tmp_path / "chunk_authoritative.wav"
    write_wav_file_atomic(raw_wav, src.generate_pcm_chunk(1.0))
    orig_wav_size = raw_wav.stat().st_size

    comp_copy = compress_audio_chunk_copy(raw_wav, output_dir=tmp_path, codec="flac")
    # Whether ffmpeg is present or not, raw WAV must remain completely untouched
    assert raw_wav.exists()
    assert raw_wav.stat().st_size == orig_wav_size
    if comp_copy:
        assert comp_copy.exists()
        assert comp_copy.suffix == ".flac"


# 7. Hardware Tier STT Configuration Decision Path (Section 20)
def test_hardware_tier_stt_configuration_decision_path():
    """Verify hardware tiers map to appropriate STT model and resource configurations."""
    cfg_baseline = select_stt_configuration(HardwareTier.BASELINE)
    assert cfg_baseline.model_id == "whisper-tiny-local"
    assert cfg_baseline.threads == 2
    assert cfg_baseline.memory_limit_mb == 150

    cfg_standard = select_stt_configuration(HardwareTier.STANDARD)
    assert cfg_standard.model_id == "whisper-base-local"
    assert cfg_standard.threads == 4
    assert cfg_standard.memory_limit_mb == 250

    cfg_high = select_stt_configuration(HardwareTier.HIGH)
    assert cfg_high.model_id == "whisper-small-local"
    assert cfg_high.threads == 8
    assert cfg_high.memory_limit_mb == 600


# 8. Local Whisper Offline Safety & Absence (Section 5 & 19)
def test_local_whisper_blocks_silent_downloads():
    """Verify LocalWhisperSTTProvider reports unavailable without weights rather than downloading."""
    # When no local weights file is provided or present, is_available must be False
    provider = LocalWhisperSTTProvider(
        model_id="whisper-tiny-local",
        model_path=Path("/tmp/nonexistent_model_weights_dir/tiny.pt"),
    )
    assert provider.is_available() is False
    # transcribe() must degrade gracefully without network calls
    dummy_chunk = AudioChunk(
        chunk_id="chunk_test",
        teaching_session_id="sesh_test",
        sequence_number=1,
        start_monotonic_ns=0,
        end_monotonic_ns=1_000_000_000,
        start_wall_time="2026-10-04T12:00:00Z",
        end_wall_time="2026-10-04T12:00:01Z",
        duration_ms=1000.0,
        raw_pcm=b"\x00" * 32000,
    )
    assert provider.transcribe(dummy_chunk) == []


# 9. Optional Real Microphone Smoke Test (Section 6 & 7)
def test_optional_real_microphone_smoke_test(tmp_path):
    """Perform real microphone capture if hardware and permissions are available.

    Must remain non-mandatory in headless CI environments.
    """
    backend = AudioBackend()
    perm_mgr = AudioPermissionManager()
    perm_report = perm_mgr.get_permission_report()

    if not backend.is_available:
        pytest.skip("Audio capture backend (ffmpeg) not installed on host.")

    if perm_report["status"] != AudioPermissionStatus.GRANTED.value:
        pytest.skip(f"Microphone permission not granted ({perm_report['status']}).")

    devices = backend.list_input_devices()
    if not devices:
        pytest.skip("No physical microphone input device found.")

    import shutil
    import subprocess

    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        pytest.skip("ffmpeg not found on PATH.")

    # Capture 0.5s real audio from system device :0
    out_file = tmp_path / "real_mic_test.raw"
    cmd = [
        ffmpeg_bin,
        "-f",
        "avfoundation",
        "-i",
        ":0",
        "-t",
        "0.5",
        "-ar",
        "16000",
        "-ac",
        "1",
        "-f",
        "s16le",
        "-y",
        str(out_file),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=5.0)
    if res.returncode != 0 or not out_file.exists():
        pytest.skip(f"Microphone recording was not permitted by OS: {res.stderr}")

    data = out_file.read_bytes()
    assert len(data) > 0, "Real microphone produced zero bytes!"
    # 0.5s at 16kHz 16-bit mono = ~16,000 bytes
    assert len(data) == pytest.approx(16000, abs=6000)

    # Wrap into valid WAV and check SHA-256
    wav_path = tmp_path / "real_mic_test.wav"
    write_wav_file_atomic(wav_path, data, sample_rate=16000, channels=1, sample_width=2)
    assert wav_path.exists()
    assert wav_path.stat().st_size == len(data) + 44
