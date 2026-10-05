"""Audio capture engine managing state transitions, stream buffering, and persistence."""

import queue
import threading
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from teach_a_skill.core.errors import StorageError
from teach_a_skill.core.logging import get_logger
from teach_a_skill.teaching.audio.buffer import BoundedAudioBuffer
from teach_a_skill.teaching.audio.sources import (
    BaseAudioSource,
    SyntheticAudioSource,
)
from teach_a_skill.teaching.audio.wav import AudioChunk, write_wav_file_atomic

logger = get_logger("teach_a_skill.teaching.audio.capture")


class AudioCaptureState(str, Enum):
    """Formal states for the audio recording lifecycle."""

    IDLE = "IDLE"
    STARTING = "STARTING"
    RECORDING = "RECORDING"
    PAUSED = "PAUSED"
    STOPPING = "STOPPING"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"
    FAILED = "FAILED"

    def __str__(self) -> str:
        return self.value


VALID_AUDIO_TRANSITIONS = {
    AudioCaptureState.IDLE: {AudioCaptureState.STARTING, AudioCaptureState.FAILED},
    AudioCaptureState.STARTING: {
        AudioCaptureState.RECORDING,
        AudioCaptureState.FAILED,
        AudioCaptureState.ABORTED,
    },
    AudioCaptureState.RECORDING: {
        AudioCaptureState.PAUSED,
        AudioCaptureState.STOPPING,
        AudioCaptureState.ABORTED,
        AudioCaptureState.FAILED,
    },
    AudioCaptureState.PAUSED: {
        AudioCaptureState.RECORDING,
        AudioCaptureState.STOPPING,
        AudioCaptureState.ABORTED,
        AudioCaptureState.FAILED,
    },
    AudioCaptureState.STOPPING: {
        AudioCaptureState.COMPLETED,
        AudioCaptureState.FAILED,
        AudioCaptureState.ABORTED,
    },
    AudioCaptureState.COMPLETED: set(),
    AudioCaptureState.ABORTED: set(),
    AudioCaptureState.FAILED: set(),
}


class AudioCaptureEngine:
    """Manages audio capture lifecycle, bounded buffering, and asynchronous disk persistence."""

    def __init__(
        self,
        teaching_session_id: str,
        audio_dir: Path,
        source: Optional[BaseAudioSource] = None,
        on_chunk_persisted: Optional[Callable[[AudioChunk], None]] = None,
    ) -> None:
        self.teaching_session_id = teaching_session_id
        self.audio_dir = audio_dir
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self.on_chunk_persisted = on_chunk_persisted

        self.state = AudioCaptureState.IDLE
        self.buffer = BoundedAudioBuffer(maxsize=100)
        self.source = source or SyntheticAudioSource(teaching_session_id)

        self._lock = threading.Lock()
        self._persister_thread: Optional[threading.Thread] = None
        self._stop_persister = threading.Event()
        self.persisted_chunks: list[AudioChunk] = []

    def transition_to(self, target: AudioCaptureState) -> None:
        """Enforces audio capture state machine rules."""
        with self._lock:
            allowed = VALID_AUDIO_TRANSITIONS.get(self.state, set())
            if target not in allowed:
                raise StorageError(
                    f"Invalid audio capture state transition from {self.state} to {target}. "
                    f"Allowed transitions: {[s.value for s in allowed]}"
                )
            self.state = target
            logger.info(f"Audio capture state changed: {self.state}")

    def start(self) -> None:
        """Start capturing and persisting audio chunks."""
        self.transition_to(AudioCaptureState.STARTING)
        self._stop_persister.clear()

        # Start persistence worker
        self._persister_thread = threading.Thread(
            target=self._persistence_worker,
            daemon=True,
            name="AudioChunkPersisterThread",
        )
        self._persister_thread.start()

        # Transition to recording and start audio source
        self.transition_to(AudioCaptureState.RECORDING)
        self.source.start(on_chunk_ready=self._on_chunk_captured)

    def pause(self) -> None:
        """Suspend audio capture."""
        if self.state != AudioCaptureState.RECORDING:
            return
        self.transition_to(AudioCaptureState.PAUSED)
        self.source.pause()

    def resume(self) -> None:
        """Resume audio capture."""
        if self.state != AudioCaptureState.PAUSED:
            return
        self.transition_to(AudioCaptureState.RECORDING)
        self.source.resume()

    def stop(self) -> list[AudioChunk]:
        """Stop capturing audio, flush queues to disk, and transition to COMPLETED."""
        if self.state in (AudioCaptureState.COMPLETED, AudioCaptureState.ABORTED):
            return self.persisted_chunks

        self.transition_to(AudioCaptureState.STOPPING)
        self.source.stop()

        # Signal persister to drain and terminate
        self.buffer.put(None)  # Poison pill
        if self._persister_thread and self._persister_thread.is_alive():
            self._persister_thread.join(timeout=5.0)

        self.transition_to(AudioCaptureState.COMPLETED)
        return self.persisted_chunks

    def cancel(self) -> list[AudioChunk]:
        """Abort capture session."""
        self.source.stop()
        self.buffer.put(None)
        if self._persister_thread and self._persister_thread.is_alive():
            self._persister_thread.join(timeout=2.0)
        self.state = AudioCaptureState.ABORTED
        return self.persisted_chunks

    def _on_chunk_captured(self, chunk: AudioChunk) -> None:
        """Callback from audio source when an in-memory chunk is complete."""
        if self.state != AudioCaptureState.RECORDING:
            return
        self.buffer.put(chunk)

    def _persistence_worker(self) -> None:
        """Worker thread popping chunks from buffer and writing them atomically to WAV."""
        while not self._stop_persister.is_set():
            try:
                chunk = self.buffer.get(timeout=0.1)
            except queue.Empty:
                continue

            if chunk is None:
                # Poison pill
                self.buffer.task_done()
                break

            target_filename = f"{chunk.chunk_id}.wav"
            target_path = self.audio_dir / target_filename

            try:
                sha256_hash, file_size = write_wav_file_atomic(
                    target_path=target_path,
                    raw_pcm=chunk.raw_pcm,
                    sample_rate=chunk.sample_rate,
                    channels=chunk.channels,
                    sample_width=chunk.sample_width,
                )
                chunk.sha256 = sha256_hash
                chunk.size_bytes = file_size
                # Clear raw pcm from memory once persisted to maintain bounded RAM
                chunk.raw_pcm = b""

                with self._lock:
                    self.persisted_chunks.append(chunk)

                if self.on_chunk_persisted:
                    self.on_chunk_persisted(chunk)

                logger.debug(
                    f"Persisted audio chunk {chunk.chunk_id} ({file_size} bytes, SHA: {sha256_hash[:8]}...)"
                )
            except Exception as e:
                logger.error(f"Failed to persist audio chunk {chunk.chunk_id}: {e}")
            finally:
                self.buffer.task_done()
