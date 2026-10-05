"""Deterministic demonstration cryptographic fingerprint generation."""

import hashlib
import json
from typing import Any

from teach_a_skill.representation.models import CanonicalEvent, DemonstrationSegment, TemporalRelation
from teach_a_skill.representation.timeline import CanonicalTimelineItem


def compute_demonstration_fingerprint(
    session_id: str,
    schema_version: str,
    canonical_events: list[CanonicalEvent],
    timeline_items: list[CanonicalTimelineItem],
    segments: list[DemonstrationSegment],
    relations: list[TemporalRelation],
) -> str:
    """Compute deterministic SHA-256 fingerprint of canonical representation."""
    h = hashlib.sha256()

    # Session and version prefix
    h.update(f"session:{session_id}|schema:{schema_version}\n".encode("utf-8"))

    # Canonical events summary
    h.update(f"events_count:{len(canonical_events)}\n".encode("utf-8"))
    if canonical_events:
        e0 = canonical_events[0]
        eN = canonical_events[-1]
        h.update(f"first_event:{e0.event_id}:{e0.relative_time_ns}\n".encode("utf-8"))
        h.update(f"last_event:{eN.event_id}:{eN.relative_time_ns}\n".encode("utf-8"))

    # Timeline summary
    h.update(f"timeline_count:{len(timeline_items)}\n".encode("utf-8"))
    for item in timeline_items[:20]:  # Sample head
        h.update(f"{item.item_id}:{item.monotonic_timestamp_ns}\n".encode("utf-8"))
    for item in timeline_items[-20:]:  # Sample tail
        h.update(f"{item.item_id}:{item.monotonic_timestamp_ns}\n".encode("utf-8"))

    # Segments & relations counts
    h.update(f"segments_count:{len(segments)}|relations_count:{len(relations)}\n".encode("utf-8"))
    for seg in segments:
        h.update(f"seg:{seg.segment_id}:{seg.start_monotonic_ns}:{seg.end_monotonic_ns}\n".encode("utf-8"))

    return h.hexdigest()
