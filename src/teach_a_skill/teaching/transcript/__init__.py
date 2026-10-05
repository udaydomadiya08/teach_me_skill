"""Transcript segments, revision store, and editing engine."""

from teach_a_skill.teaching.transcript.editor import TranscriptEditor
from teach_a_skill.teaching.transcript.segment import TranscriptCorrection, TranscriptSegment
from teach_a_skill.teaching.transcript.store import TranscriptStore

__all__ = [
    "TranscriptSegment",
    "TranscriptCorrection",
    "TranscriptStore",
    "TranscriptEditor",
]
