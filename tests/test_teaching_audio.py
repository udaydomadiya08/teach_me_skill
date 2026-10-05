"""Tests for Phase 3 Audio Capture and Processing Subsystem."""

import time
from pathlib import Path

import pytest

from teach_a_skill.core.errors import StorageError
from teach_a_skill.teaching.audio.buffer import BoundedAudioBuffer
from teach_a_skill.teaching.audio.capture import AudioCaptureEngine, AudioCaptureState
from teach_a_skill.teaching.audio.device import AudioBackend, AudioDevice
from teach_a_skill.teaching.audio.permissions import AudioPermissionManager, AudioPermissionStatus
from teach_a_skill.teaching.audio.sources import SyntheticAudioSource
from teach_a_skill.teaching.audio.wav import (
    AudioChunk,
    decode_wav_file,
    encode_pcm_to_wav_bytes,
    write_wav_file_atomic,
)


def test_audio_chunk_wav_encoding_and_sha256(temp_dir: Path):
    """Test pure stdlib WAV encode/decode and atomic write with SHA-256."""
    sample_rate = 16000
    channels = 1
    sample_width = 2
    # 0.5s of 16-bit PCM = 8000 samples = 16000 bytes
    pcm_bytes = b"\x05\x00" * 8000

    wav_bytes = encode_pcm_to_wav_bytes(pcm_bytes, sample_rate, channels, sample_width)
    assert len(wav_bytes) == len(pcm_bytes) + 44
    assert wav_bytes[:4] == b"RIFF"
    assert wav_bytes[8:12] == b"WAVE"

    target_file = temp_dir / "test_chunk.wav"
    sha, size = write_wav_file_atomic(target_file, pcm_bytes, sample_rate, channels, sample_width)
    assert target_file.exists()
    assert size == len(pcm_bytes) + 44
    assert len(sha) == 64

    # Decode and verify roundtrip
    decoded_pcm, sr, ch, sw = decode_wav_file(target_file)
    assert decoded_pcm == pcm_bytes
    assert sr == sample_rate
    assert ch == channels
    assert sw == sample_width


def test_audio_chunk_metadata_dict():
    """Test AudioChunk metadata exclusion of raw PCM."""
    chunk = AudioChunk(
        chunk_id="chunk_001",
        teaching_session_id="sesh_01",
        sequence_number=1,
        start_monotonic_ns=100,
        end_monotonic_ns=200,
        start_wall_time="2026-10-04T12:00:00Z",
        end_wall_time="2026-10-04T12:00:01Z",
        duration_ms=1000.0,
        raw_pcm=b"\x00\x00" * 100,
    )
    d = chunk.to_metadata_dict()
    assert "raw_pcm" not in d
    assert d["chunk_id"] == "chunk_001"
    assert d["sequence_number"] == 1


def test_bounded_audio_buffer():
    """Test bounded audio buffer queue limits and metrics."""
    buf = BoundedAudioBuffer(maxsize=2)
    assert buf.metrics.current_size == 0

    c1 = AudioChunk(
        chunk_id="c1",
        teaching_session_id="s",
        sequence_number=1,
        start_monotonic_ns=1,
        end_monotonic_ns=2,
        start_wall_time="w1",
        end_wall_time="w2",
        duration_ms=10.0,
        size_bytes=100,
        raw_pcm=b"\x00" * 100,
    )
    assert buf.put(c1) is True
    assert buf.metrics.chunks_enqueued == 1
    assert buf.metrics.current_size == 1

    c2 = AudioChunk(
        chunk_id="c2",
        teaching_session_id="s",
        sequence_number=2,
        start_monotonic_ns=3,
        end_monotonic_ns=4,
        start_wall_time="w3",
        end_wall_time="w4",
        duration_ms=10.0,
        size_bytes=100,
        raw_pcm=b"\x00" * 100,
    )
    assert buf.put(c2) is True
    assert buf.metrics.chunks_enqueued == 2
    assert buf.metrics.current_size == 2

    # Queue is full with maxsize=2
    c3 = AudioChunk(
        chunk_id="c3",
        teaching_session_id="s",
        sequence_number=3,
        start_monotonic_ns=5,
        end_monotonic_ns=6,
        start_wall_time="w5",
        end_wall_time="w6",
        duration_ms=10.0,
        size_bytes=100,
        raw_pcm=b"\x00" * 100,
    )
    # Block timeout small so it drops
    assert buf.put(c3, block=True, timeout=0.01) is False
    assert buf.metrics.chunks_dropped == 1

    popped = buf.get(timeout=0.1)
    assert popped == c1
    buf.task_done()
    assert buf.metrics.chunks_persisted == 1


def test_synthetic_audio_source():
    """Test deterministic synthetic audio source generator."""
    received = []
    src = SyntheticAudioSource(
        teaching_session_id="test_sesh",
        chunk_duration_sec=0.05,
        sample_rate=16000,
        frequency_hz=440.0,
    )
    assert src.is_active is False
    src.start(on_chunk_ready=lambda c: received.append(c))
    assert src.is_active is True

    time.sleep(0.2)
    src.stop()
    assert src.is_active is False
    assert len(received) >= 2
    c = received[0]
    assert c.sample_rate == 16000
    assert c.duration_ms == pytest.approx(50.0, rel=0.3)
    assert c.start_monotonic_ns < c.end_monotonic_ns
    assert len(c.raw_pcm) > 0


def test_audio_capture_engine_lifecycle(temp_dir: Path):
    """Test AudioCaptureEngine state machine and streaming write."""
    dest_dir = temp_dir / "audio_stream"
    source = SyntheticAudioSource(
        teaching_session_id="test_engine_sesh",
        chunk_duration_sec=0.05,
    )
    engine = AudioCaptureEngine(
        teaching_session_id="test_engine_sesh",
        audio_dir=dest_dir,
        source=source,
    )

    assert engine.state == AudioCaptureState.IDLE

    # Start
    engine.start()
    assert engine.state == AudioCaptureState.RECORDING

    time.sleep(0.2)

    # Pause
    engine.pause()
    assert engine.state == AudioCaptureState.PAUSED
    count_at_pause = len(engine.persisted_chunks)
    time.sleep(0.1)

    # Resume
    engine.resume()
    assert engine.state == AudioCaptureState.RECORDING
    time.sleep(0.15)

    # Stop
    chunks = engine.stop()
    assert engine.state == AudioCaptureState.COMPLETED
    assert len(chunks) >= count_at_pause

    # Verify persisted WAV files on disk
    for c in chunks:
        wav_path = dest_dir / f"{c.chunk_id}.wav"
        assert wav_path.exists()
        assert c.sha256 != ""
        assert c.size_bytes > 44


def test_audio_capture_invalid_transitions(temp_dir: Path):
    """Test state machine rejects illegal transitions with StorageError."""
    source = SyntheticAudioSource(
        teaching_session_id="test_invalid",
        chunk_duration_sec=0.05,
    )
    engine = AudioCaptureEngine(
        teaching_session_id="test_invalid",
        audio_dir=temp_dir / "audio_invalid",
        source=source,
    )

    # Invalid: cannot pause from IDLE (pause() no-ops if not RECORDING)
    engine.pause()
    assert engine.state == AudioCaptureState.IDLE

    # Invalid transition via transition_to
    with pytest.raises(StorageError):
        engine.transition_to(AudioCaptureState.PAUSED)

    engine.start()
    assert engine.state == AudioCaptureState.RECORDING

    # Invalid: cannot jump directly from RECORDING to COMPLETED
    with pytest.raises(StorageError):
        engine.transition_to(AudioCaptureState.COMPLETED)

    engine.stop()
    assert engine.state == AudioCaptureState.COMPLETED


def test_audio_device_and_permission_manager():
    """Test audio device discovery and permission handling."""
    mgr = AudioPermissionManager()
    status = mgr.check_permission()
    assert isinstance(status, AudioPermissionStatus)

    backend = AudioBackend()
    devices = backend.list_input_devices()
    assert isinstance(devices, list)
    for dev in devices:
        assert isinstance(dev, AudioDevice)
        assert dev.device_id != ""
