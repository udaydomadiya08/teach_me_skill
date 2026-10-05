"""Transcript editor for non-destructive corrections, segment splitting, merging, and revisioning."""

import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from teach_a_skill.core.errors import StorageError
from teach_a_skill.core.logging import get_logger
from teach_a_skill.teaching.transcript.segment import TranscriptCorrection, TranscriptSegment
from teach_a_skill.teaching.transcript.store import TranscriptStore

logger = get_logger("teach_a_skill.teaching.transcript.editor")


class TranscriptEditor:
    """Provides non-destructive editing operations for transcript evidence."""

    def __init__(self, store: TranscriptStore) -> None:
        self.store = store

    def edit_segment(
        self,
        segment_id: str,
        new_text: str,
        reason: Optional[str] = None,
    ) -> TranscriptSegment:
        """Correct or edit the text of an existing transcript segment.

        Increments the revision number and records an audit entry.
        """
        segments = self.store.read_all_segments(only_active=False)
        target_seg = None
        for s in segments:
            if s.segment_id == segment_id:
                target_seg = s
                break

        if not target_seg:
            raise StorageError(f"Transcript segment not found: '{segment_id}'")

        previous_text = target_seg.text
        target_seg.text = new_text
        target_seg.revision += 1
        target_seg.edited_at = datetime.now(timezone.utc).isoformat()

        # Record correction audit trail
        corr = TranscriptCorrection(
            correction_id=f"corr_{uuid.uuid4().hex[:10]}",
            teaching_session_id=target_seg.teaching_session_id,
            segment_id=segment_id,
            previous_text=previous_text,
            new_text=new_text,
            revision=target_seg.revision,
            timestamp=target_seg.edited_at,
            monotonic_timestamp_ns=time.monotonic_ns(),
            action="edit",
            reason=reason,
        )

        self.store.record_correction(corr)
        self.store.rewrite_active_segments(segments)
        logger.info(f"Edited transcript segment {segment_id} -> Rev {target_seg.revision}")
        return target_seg

    def split_segment(
        self,
        segment_id: str,
        split_monotonic_ns: int,
        text_part1: str,
        text_part2: str,
        reason: Optional[str] = None,
    ) -> tuple[TranscriptSegment, TranscriptSegment]:
        """Split a single segment into two contiguous sub-segments."""
        segments = self.store.read_all_segments(only_active=False)
        target_idx = -1
        for idx, s in enumerate(segments):
            if s.segment_id == segment_id:
                target_idx = idx
                break

        if target_idx == -1:
            raise StorageError(f"Transcript segment not found: '{segment_id}'")

        orig = segments[target_idx]
        if not (orig.start_monotonic_ns < split_monotonic_ns < orig.end_monotonic_ns):
            raise StorageError(
                f"Split timestamp {split_monotonic_ns} must lie strictly within "
                f"[{orig.start_monotonic_ns}, {orig.end_monotonic_ns}]."
            )

        now_wall = datetime.now(timezone.utc).isoformat()

        # Sub-segment 1
        seg1 = TranscriptSegment(
            segment_id=f"{orig.segment_id}_a",
            teaching_session_id=orig.teaching_session_id,
            sequence_number=orig.sequence_number,
            start_monotonic_ns=orig.start_monotonic_ns,
            end_monotonic_ns=split_monotonic_ns,
            start_wall_time=orig.start_wall_time,
            end_wall_time=now_wall,
            text=text_part1,
            language=orig.language,
            confidence=orig.confidence,
            source=orig.source,
            audio_chunk_ids=orig.audio_chunk_ids,
            revision=orig.revision + 1,
            is_active=True,
            edited_at=now_wall,
        )

        # Sub-segment 2
        seg2 = TranscriptSegment(
            segment_id=f"{orig.segment_id}_b",
            teaching_session_id=orig.teaching_session_id,
            sequence_number=orig.sequence_number + 1,
            start_monotonic_ns=split_monotonic_ns,
            end_monotonic_ns=orig.end_monotonic_ns,
            start_wall_time=now_wall,
            end_wall_time=orig.end_wall_time,
            text=text_part2,
            language=orig.language,
            confidence=orig.confidence,
            source=orig.source,
            audio_chunk_ids=orig.audio_chunk_ids,
            revision=orig.revision + 1,
            is_active=True,
            edited_at=now_wall,
        )

        # Soft-deactivate original and insert new sub-segments
        orig.is_active = False
        segments.insert(target_idx + 1, seg2)
        segments.insert(target_idx + 1, seg1)

        corr = TranscriptCorrection(
            correction_id=f"corr_{uuid.uuid4().hex[:10]}",
            teaching_session_id=orig.teaching_session_id,
            segment_id=segment_id,
            previous_text=orig.text,
            new_text=f"{text_part1} | {text_part2}",
            revision=orig.revision + 1,
            timestamp=now_wall,
            monotonic_timestamp_ns=time.monotonic_ns(),
            action="split",
            reason=reason,
        )
        self.store.record_correction(corr)
        self.store.rewrite_active_segments(segments)
        logger.info(f"Split segment {segment_id} into {seg1.segment_id} and {seg2.segment_id}")
        return seg1, seg2

    def merge_segments(
        self,
        segment_id1: str,
        segment_id2: str,
        merged_text: str,
        reason: Optional[str] = None,
    ) -> TranscriptSegment:
        """Merge two adjacent segments into one."""
        segments = self.store.read_all_segments(only_active=False)
        s1 = next((s for s in segments if s.segment_id == segment_id1), None)
        s2 = next((s for s in segments if s.segment_id == segment_id2), None)

        if not s1 or not s2:
            raise StorageError(
                f"Cannot merge: segments '{segment_id1}' or '{segment_id2}' not found."
            )

        now_wall = datetime.now(timezone.utc).isoformat()
        all_chunks = list(dict.fromkeys(s1.audio_chunk_ids + s2.audio_chunk_ids))

        merged_seg = TranscriptSegment(
            segment_id=f"seg_{uuid.uuid4().hex[:8]}",
            teaching_session_id=s1.teaching_session_id,
            sequence_number=s1.sequence_number,
            start_monotonic_ns=min(s1.start_monotonic_ns, s2.start_monotonic_ns),
            end_monotonic_ns=max(s1.end_monotonic_ns, s2.end_monotonic_ns),
            start_wall_time=s1.start_wall_time,
            end_wall_time=s2.end_wall_time,
            text=merged_text,
            language=s1.language,
            confidence=None,
            source=s1.source,
            audio_chunk_ids=all_chunks,
            revision=max(s1.revision, s2.revision) + 1,
            is_active=True,
            edited_at=now_wall,
        )

        s1.is_active = False
        s2.is_active = False
        segments.append(merged_seg)

        corr = TranscriptCorrection(
            correction_id=f"corr_{uuid.uuid4().hex[:10]}",
            teaching_session_id=s1.teaching_session_id,
            segment_id=f"{segment_id1}+{segment_id2}",
            previous_text=f"{s1.text} | {s2.text}",
            new_text=merged_text,
            revision=merged_seg.revision,
            timestamp=now_wall,
            monotonic_timestamp_ns=time.monotonic_ns(),
            action="merge",
            reason=reason,
        )
        self.store.record_correction(corr)
        self.store.rewrite_active_segments(segments)
        logger.info(f"Merged segments {segment_id1} and {segment_id2} into {merged_seg.segment_id}")
        return merged_seg

    def hide_segment(self, segment_id: str, reason: Optional[str] = None) -> None:
        """Non-destructively soft-delete a transcript segment."""
        segments = self.store.read_all_segments(only_active=False)
        target = next((s for s in segments if s.segment_id == segment_id), None)
        if not target:
            raise StorageError(f"Transcript segment not found: '{segment_id}'")

        target.is_active = False
        target.edited_at = datetime.now(timezone.utc).isoformat()

        corr = TranscriptCorrection(
            correction_id=f"corr_{uuid.uuid4().hex[:10]}",
            teaching_session_id=target.teaching_session_id,
            segment_id=segment_id,
            previous_text=target.text,
            new_text="[HIDDEN]",
            revision=target.revision + 1,
            timestamp=target.edited_at,
            monotonic_timestamp_ns=time.monotonic_ns(),
            action="hide",
            reason=reason,
        )
        self.store.record_correction(corr)
        self.store.rewrite_active_segments(segments)
        logger.info(f"Hidden segment {segment_id}")
