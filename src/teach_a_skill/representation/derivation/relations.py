"""Deterministic temporal and physical evidence relation builder."""

import bisect
from typing import Any

from teach_a_skill.representation.models import (
    CanonicalEvent,
    ClickInteraction,
    DoubleClickInteraction,
    DragSequence,
    KeyboardShortcutSequence,
    TemporalRelation,
    TemporalRelationType,
    TextInputSequence,
)


def build_temporal_relations(
    events: list[CanonicalEvent],
    frames: list[dict[str, Any]],
    speech_segments: list[dict[str, Any]],
    annotations: list[dict[str, Any]],
    clicks: list[ClickInteraction],
    drags: list[DragSequence],
    shortcuts: list[KeyboardShortcutSequence],
    text_inputs: list[TextInputSequence],
    session_id: str,
) -> list[TemporalRelation]:
    """Construct deterministic physical and temporal relationships across modalities."""
    relations: list[TemporalRelation] = []

    # 1. Structural CONTAINS relations (Derived interactions -> Raw events)
    for c in clicks:
        relations.append(
            TemporalRelation(
                relation_id=f"rel_{len(relations) + 1:06d}",
                source_id=c.interaction_id,
                source_type="click_interaction",
                target_id=c.down_event_id,
                target_type="canonical_event",
                relation_type=TemporalRelationType.CONTAINS,
                delta_ms=0.0,
                provenance={"session_id": session_id},
            )
        )
        relations.append(
            TemporalRelation(
                relation_id=f"rel_{len(relations) + 1:06d}",
                source_id=c.interaction_id,
                source_type="click_interaction",
                target_id=c.up_event_id,
                target_type="canonical_event",
                relation_type=TemporalRelationType.CONTAINS,
                delta_ms=c.duration_ms,
                provenance={"session_id": session_id},
            )
        )

    for d in drags:
        relations.append(
            TemporalRelation(
                relation_id=f"rel_{len(relations) + 1:06d}",
                source_id=d.sequence_id,
                source_type="drag_sequence",
                target_id=d.down_event_id,
                target_type="canonical_event",
                relation_type=TemporalRelationType.CONTAINS,
                delta_ms=0.0,
                provenance={"session_id": session_id},
            )
        )
        relations.append(
            TemporalRelation(
                relation_id=f"rel_{len(relations) + 1:06d}",
                source_id=d.sequence_id,
                source_type="drag_sequence",
                target_id=d.up_event_id,
                target_type="canonical_event",
                relation_type=TemporalRelationType.CONTAINS,
                delta_ms=d.duration_ms,
                provenance={"session_id": session_id},
            )
        )

    for sc in shortcuts:
        for eid in sc.event_ids:
            relations.append(
                TemporalRelation(
                    relation_id=f"rel_{len(relations) + 1:06d}",
                    source_id=sc.sequence_id,
                    source_type="shortcut_sequence",
                    target_id=eid,
                    target_type="canonical_event",
                    relation_type=TemporalRelationType.CONTAINS,
                    delta_ms=0.0,
                    provenance={"session_id": session_id},
                )
            )

    # 2. NEAREST_FRAME relations (Events -> Screen Frames)
    if frames:
        frame_times = [int(f.get("monotonic_timestamp", 0.0) * 1_000_000_000) for f in frames]
        for ev in events:
            # Only connect discrete interactions (clicks, keys, focus) to avoid flooding with every move
            if ev.canonical_event_type.value in (
                "CLICK",
                "DOUBLE_CLICK",
                "POINTER_DOWN",
                "KEY_DOWN",
                "SHORTCUT",
                "WINDOW_FOCUS",
            ):
                idx = bisect.bisect_left(frame_times, ev.relative_time_ns)
                nearest_f = None
                if idx == 0:
                    nearest_f = frames[0]
                elif idx >= len(frames):
                    nearest_f = frames[-1]
                else:
                    d_before = abs(frame_times[idx - 1] - ev.relative_time_ns)
                    d_after = abs(frame_times[idx] - ev.relative_time_ns)
                    nearest_f = frames[idx - 1] if d_before <= d_after else frames[idx]

                if nearest_f:
                    f_ns = int(nearest_f.get("monotonic_timestamp", 0.0) * 1_000_000_000)
                    delta_ms = (f_ns - ev.relative_time_ns) / 1_000_000.0
                    relations.append(
                        TemporalRelation(
                            relation_id=f"rel_{len(relations) + 1:06d}",
                            source_id=ev.event_id,
                            source_type="canonical_event",
                            target_id=nearest_f.get("frame_id", ""),
                            target_type="screen_frame",
                            relation_type=TemporalRelationType.NEAREST,
                            delta_ms=round(delta_ms, 2),
                            provenance={"session_id": session_id},
                        )
                    )

    # 3. OVERLAPS relations (Events with Speech Segments)
    if speech_segments and events:
        event_times = [ev.relative_time_ns for ev in events]
        for sp in speech_segments:
            sp_id = sp.get("segment_id", "")
            sp_start_ns = sp.get("start_monotonic_ns", 0)
            sp_end_ns = sp.get("end_monotonic_ns", 0)

            i_start = bisect.bisect_left(event_times, sp_start_ns)
            i_end = bisect.bisect_right(event_times, sp_end_ns)

            for ev in events[i_start:i_end]:
                relations.append(
                    TemporalRelation(
                        relation_id=f"rel_{len(relations) + 1:06d}",
                        source_id=sp_id,
                        source_type="speech_segment",
                        target_id=ev.event_id,
                        target_type="canonical_event",
                        relation_type=TemporalRelationType.OVERLAPS,
                        delta_ms=round((ev.relative_time_ns - sp_start_ns) / 1_000_000.0, 2),
                        provenance={"session_id": session_id},
                    )
                )

    # 4. OVERLAPS / CONTAINS relations (Teaching Annotations with Events)
    for ann in annotations:
        ann_id = ann.get("annotation_id", "")
        ann_start_ns = ann.get("start_monotonic_ns", 0)
        ann_end_ns = ann.get("end_monotonic_ns", 0)
        ref_event_ids = ann.get("references", {}).get("event_ids", [])

        # Explicit reference by user
        for ref_eid in ref_event_ids:
            relations.append(
                TemporalRelation(
                    relation_id=f"rel_{len(relations) + 1:06d}",
                    source_id=ann_id,
                    source_type="teaching_annotation",
                    target_id=ref_eid,
                    target_type="canonical_event",
                    relation_type=TemporalRelationType.CONTAINS,
                    delta_ms=0.0,
                    provenance={"session_id": session_id, "explicit_user_reference": True},
                )
            )

        # Temporal proximity overlap
        for ev in events:
            if ann_start_ns <= ev.relative_time_ns <= ann_end_ns and ev.event_id not in ref_event_ids:
                relations.append(
                    TemporalRelation(
                        relation_id=f"rel_{len(relations) + 1:06d}",
                        source_id=ann_id,
                        source_type="teaching_annotation",
                        target_id=ev.event_id,
                        target_type="canonical_event",
                        relation_type=TemporalRelationType.OVERLAPS,
                        delta_ms=round((ev.relative_time_ns - ann_start_ns) / 1_000_000.0, 2),
                        provenance={"session_id": session_id},
                    )
                )

    return relations
