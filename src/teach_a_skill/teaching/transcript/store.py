"""Transcript persistence store managing streaming JSONL and revision history."""

import json
import threading
from pathlib import Path
from typing import Optional

from teach_a_skill.core.logging import get_logger
from teach_a_skill.teaching.transcript.segment import TranscriptCorrection, TranscriptSegment

logger = get_logger("teach_a_skill.teaching.transcript.store")


class TranscriptStore:
    """Manages streaming JSONL append and revision history for transcript segments."""

    def __init__(self, transcript_file: Path, corrections_file: Optional[Path] = None) -> None:
        self.transcript_file = transcript_file
        self.corrections_file = corrections_file or transcript_file.parent / "corrections.jsonl"
        self._lock = threading.Lock()

        self.transcript_file.parent.mkdir(parents=True, exist_ok=True)
        self._transcript_handle = None
        self._corrections_handle = None

    def append_segment(self, segment: TranscriptSegment) -> None:
        """Append a new transcript segment to transcript.jsonl with immediate flush."""
        with self._lock:
            if self._transcript_handle is None or self._transcript_handle.closed:
                self._transcript_handle = open(self.transcript_file, "a", encoding="utf-8")
            self._transcript_handle.write(segment.to_json() + "\n")
            self._transcript_handle.flush()

    def append_segments(self, segments: list[TranscriptSegment]) -> None:
        """Batch append multiple segments."""
        with self._lock:
            if self._transcript_handle is None or self._transcript_handle.closed:
                self._transcript_handle = open(self.transcript_file, "a", encoding="utf-8")
            for seg in segments:
                self._transcript_handle.write(seg.to_json() + "\n")
            self._transcript_handle.flush()

    def record_correction(self, correction: TranscriptCorrection) -> None:
        """Record an audit trail correction entry into corrections.jsonl."""
        with self._lock:
            if self._corrections_handle is None or self._corrections_handle.closed:
                self._corrections_handle = open(self.corrections_file, "a", encoding="utf-8")
            self._corrections_handle.write(correction.to_json() + "\n")
            self._corrections_handle.flush()

    def read_all_segments(self, only_active: bool = True) -> list[TranscriptSegment]:
        """Read all transcript segments from disk.

        If only_active is True, returns only segments where is_active is True.
        """
        if not self.transcript_file.exists():
            return []

        segments: list[TranscriptSegment] = []
        with open(self.transcript_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    data = json.loads(line)
                    seg = TranscriptSegment.from_dict(data)
                    if not only_active or seg.is_active:
                        segments.append(seg)
        return segments

    def read_all_corrections(self) -> list[TranscriptCorrection]:
        """Read full audit history from corrections.jsonl."""
        if not self.corrections_file.exists():
            return []

        corrections: list[TranscriptCorrection] = []
        with open(self.corrections_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    data = json.loads(line)
                    corrections.append(TranscriptCorrection.from_dict(data))
        return corrections

    def rewrite_active_segments(self, segments: list[TranscriptSegment]) -> None:
        """Atomically rewrite transcript.jsonl with updated revisions/states."""
        with self._lock:
            self.close()
            tmp_file = self.transcript_file.with_suffix(".tmp")
            with open(tmp_file, "w", encoding="utf-8") as f:
                for seg in segments:
                    f.write(seg.to_json() + "\n")
                f.flush()
            tmp_file.replace(self.transcript_file)

    def close(self) -> None:
        """Flush and close active file handles."""
        if self._transcript_handle and not self._transcript_handle.closed:
            self._transcript_handle.flush()
            self._transcript_handle.close()
            self._transcript_handle = None
        if self._corrections_handle and not self._corrections_handle.closed:
            self._corrections_handle.flush()
            self._corrections_handle.close()
            self._corrections_handle = None
