"""Pure Python standard library energy-based Voice Activity Detection (VAD)."""

import math
import struct


class EnergyVAD:
    """Deterministic, lightweight energy and zero-crossing rate VAD.

    Runs with near-zero CPU and zero memory overhead to identify speech intervals.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        frame_duration_ms: int = 30,
        energy_threshold_rms: float = 350.0,
        min_speech_duration_ms: int = 250,
        min_silence_duration_ms: int = 400,
    ) -> None:
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.energy_threshold_rms = energy_threshold_rms
        self.min_speech_duration_ms = min_speech_duration_ms
        self.min_silence_duration_ms = min_silence_duration_ms

        self.frame_size_samples = int(sample_rate * (frame_duration_ms / 1000.0))
        self.frame_size_bytes = self.frame_size_samples * 2  # 16-bit mono = 2 bytes per sample

    def detect_speech_intervals(self, raw_pcm: bytes) -> list[tuple[float, float]]:
        """Analyze raw 16-bit mono PCM bytes and return list of (start_sec, end_sec) speech segments."""
        if not raw_pcm:
            return []

        num_frames = len(raw_pcm) // self.frame_size_bytes
        frame_results: list[bool] = []

        for f_idx in range(num_frames):
            offset = f_idx * self.frame_size_bytes
            frame_bytes = raw_pcm[offset : offset + self.frame_size_bytes]

            # Calculate RMS energy
            count = len(frame_bytes) // 2
            if count == 0:
                frame_results.append(False)
                continue

            samples = struct.unpack(f"<{count}h", frame_bytes)
            sum_sq = sum(s * s for s in samples)
            rms = math.sqrt(sum_sq / count)

            # Frame is active if RMS exceeds threshold
            frame_results.append(rms >= self.energy_threshold_rms)

        # Merge contiguous active frames into intervals with smoothing
        intervals: list[tuple[float, float]] = []
        in_speech = False
        speech_start_sec = 0.0
        silence_frames = 0
        max_silence_frames = int(self.min_silence_duration_ms / self.frame_duration_ms)
        min_speech_frames = int(self.min_speech_duration_ms / self.frame_duration_ms)

        current_speech_frames = 0

        for f_idx, is_active in enumerate(frame_results):
            t_sec = f_idx * (self.frame_duration_ms / 1000.0)

            if is_active:
                if not in_speech:
                    in_speech = True
                    speech_start_sec = t_sec
                    current_speech_frames = 0
                silence_frames = 0
                current_speech_frames += 1
            else:
                if in_speech:
                    silence_frames += 1
                    if silence_frames >= max_silence_frames:
                        # End of speech interval
                        speech_end_sec = t_sec
                        if current_speech_frames >= min_speech_frames:
                            intervals.append((speech_start_sec, speech_end_sec))
                        in_speech = False
                        silence_frames = 0

        if in_speech and current_speech_frames >= min_speech_frames:
            intervals.append((speech_start_sec, num_frames * (self.frame_duration_ms / 1000.0)))

        return intervals
