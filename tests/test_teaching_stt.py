"""Tests for Phase 3 Speech-to-Text provider abstractions, VAD, and async queue."""

import time

import pytest

from teach_a_skill.teaching.audio.wav import AudioChunk
from teach_a_skill.teaching.stt.local_whisper import LocalWhisperSTTProvider
from teach_a_skill.teaching.stt.mock_provider import MockSTTProvider
from teach_a_skill.teaching.stt.provider import ISpeechToTextProvider
from teach_a_skill.teaching.stt.vad import EnergyVAD
from teach_a_skill.teaching.stt.worker import AsyncTranscriptionWorker


def _make_dummy_chunk(
    seq: int = 1, duration_ms: float = 1000.0, raw_pcm: bytes = b""
) -> AudioChunk:
    return AudioChunk(
        chunk_id=f"chk_{seq:03d}",
        teaching_session_id="test_sesh",
        sequence_number=seq,
        start_monotonic_ns=seq * 1_000_000_000,
        end_monotonic_ns=(seq + 1) * 1_000_000_000,
        start_wall_time="2026-10-04T12:00:00Z",
        end_wall_time="2026-10-04T12:00:01Z",
        duration_ms=duration_ms,
        sample_rate=16000,
        channels=1,
        sample_width=2,
        size_bytes=len(raw_pcm) + 44,
        raw_pcm=raw_pcm or (b"\x00\x00" * int(16000 * (duration_ms / 1000.0))),
    )


def test_mock_stt_provider_contract():
    """Verify MockSTTProvider conforms to ISpeechToTextProvider contract."""
    provider = MockSTTProvider(model_id="whisper-tiny-local", simulated_latency_sec=0.0)
    assert isinstance(provider, ISpeechToTextProvider)
    assert provider.provider_id == "mock-stt"
    assert provider.model_id == "whisper-tiny-local"
    assert provider.is_available() is True
    assert provider.supports_timestamps() is True
    assert provider.supports_confidence() is True
    assert provider.estimated_memory_mb() > 0
    assert "en" in provider.supported_languages()

    provider.load()
    chunk = _make_dummy_chunk(seq=1, duration_ms=1000.0)
    segments = provider.transcribe(chunk, language="en")
    assert len(segments) > 0
    seg = segments[0]
    assert seg.sequence_number == 1
    assert seg.teaching_session_id == "test_sesh"
    assert seg.start_monotonic_ns == chunk.start_monotonic_ns
    assert seg.text != ""
    assert seg.confidence is not None
    assert seg.confidence > 0.0

    provider.unload()


def test_local_whisper_provider_offline_contract():
    """Verify LocalWhisperSTTProvider handles missing local binary gracefully."""
    # Deliberately point to nonexistent binary
    provider = LocalWhisperSTTProvider(
        model_id="whisper-base-local",
        binary_path="/usr/local/bin/nonexistent_whisper_binary_12345",
    )
    assert isinstance(provider, ISpeechToTextProvider)
    assert provider.provider_id == "local-whisper"
    assert provider.is_available() is False
    assert provider.supports_timestamps() is True

    # Loading nonexistent binary should not raise an unhandled crash
    provider.load()
    chunk = _make_dummy_chunk(seq=1)
    segments = provider.transcribe(chunk)
    assert segments == []  # Degrades gracefully
    provider.unload()


def test_energy_vad_speech_vs_silence():
    """Test standard library energy VAD on pure silence vs synthetic tone."""
    vad = EnergyVAD(sample_rate=16000, energy_threshold_rms=200.0)

    # 1 second of total silence
    silence_pcm = b"\x00\x00" * 16000
    silence_intervals = vad.detect_speech_intervals(silence_pcm)
    assert len(silence_intervals) == 0

    # 1 second with 500ms of loud tone (amplitude 2000) followed by 500ms silence
    loud_samples = b"\x80\x07" * 8000  # 0x0780 = 1920 in 16-bit little-endian
    mixed_pcm = loud_samples + (b"\x00\x00" * 8000)
    speech_intervals = vad.detect_speech_intervals(mixed_pcm)
    assert len(speech_intervals) >= 1
    start_sec, end_sec = speech_intervals[0]
    assert start_sec == pytest.approx(0.0, abs=0.1)
    assert end_sec >= 0.3


def test_async_transcription_worker_queue_and_metrics():
    """Test asynchronous transcription queue, backlog tracking, and callback delivery."""
    delivered_segments = []
    provider = MockSTTProvider(simulated_latency_sec=0.01)

    worker = AsyncTranscriptionWorker(
        provider=provider,
        on_segments_ready=lambda segs: delivered_segments.extend(segs),
        max_queue_size=10,
    )
    worker.start()

    # Enqueue 3 chunks
    for i in range(1, 4):
        c = _make_dummy_chunk(seq=i, duration_ms=500.0)
        enqueued = worker.enqueue_chunk(c)
        assert enqueued is True

    # Wait for processing
    time.sleep(0.15)
    worker.stop(timeout=1.0)

    assert len(delivered_segments) == 3
    assert worker.metrics.total_chunks_processed == 3
    assert worker.metrics.total_segments_produced == 3
    assert worker.metrics.audio_duration_sec == pytest.approx(1.5, rel=1e-2)
    assert worker.metrics.real_time_factor >= 0.0
