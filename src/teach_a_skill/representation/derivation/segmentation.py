"""Deterministic demonstration segmentation based on physical and context boundaries."""

from typing import Any, Optional

from teach_a_skill.representation.models import (
    ApplicationTransition,
    CanonicalEvent,
    CanonicalEventType,
    DemonstrationSegment,
    IdleInterval,
)


def derive_demonstration_segments(
    events: list[CanonicalEvent],
    app_transitions: list[ApplicationTransition],
    idle_intervals: list[IdleInterval],
    speech_segments: list[dict[str, Any]],
    annotations: list[dict[str, Any]],
    frames: list[dict[str, Any]],
    total_duration_sec: float,
) -> list[DemonstrationSegment]:
    """Segment demonstration deterministically along physical boundary milestones.

    Triggers:
    1. Session start / end
    2. Application focus change
    3. Significant inactivity / idle interval (>= 5.0s)
    4. Explicit user teaching annotation
    """
    if not events and total_duration_sec <= 0:
        return []

    session_end_ns = int(total_duration_sec * 1_000_000_000)
    if events and events[-1].relative_time_ns > session_end_ns:
        session_end_ns = events[-1].relative_time_ns

    # Collect boundary cut-points: (timestamp_ns, trigger_name)
    cutpoints: list[tuple[int, str]] = [(0, "session_start")]

    # 1. Application switch boundaries
    for trans in app_transitions:
        if trans.monotonic_timestamp_ns > 0:
            cutpoints.append((trans.monotonic_timestamp_ns, f"application_switch:{trans.to_application}"))

    # 2. Significant idle period boundaries (>= 4.0s)
    for idle in idle_intervals:
        if idle.duration_ms >= 4000.0:
            cutpoints.append((idle.start_monotonic_ns, "idle_start"))
            cutpoints.append((idle.end_monotonic_ns, "idle_end"))

    # 3. Explicit annotations
    for ann in annotations:
        t_ns = ann.get("start_monotonic_ns", 0)
        if t_ns > 0:
            cutpoints.append((t_ns, "annotation_milestone"))

    # Add final end point
    cutpoints.append((session_end_ns, "session_end"))

    # Deduplicate and sort cutpoints by timestamp
    cutpoints = sorted(cutpoints, key=lambda cp: cp[0])
    filtered_cuts: list[tuple[int, str]] = []
    MIN_SEGMENT_GAP_NS = 500_000_000  # Minimum 500ms segment length to prevent micro-splinters

    for cp in cutpoints:
        if not filtered_cuts:
            filtered_cuts.append(cp)
        else:
            prev_t = filtered_cuts[-1][0]
            if cp[0] - prev_t >= MIN_SEGMENT_GAP_NS:
                filtered_cuts.append(cp)

    if filtered_cuts[-1][0] < session_end_ns:
        filtered_cuts.append((session_end_ns, "session_end"))

    # Construct segments between adjacent cutpoints
    segments: list[DemonstrationSegment] = []
    for idx in range(len(filtered_cuts) - 1):
        seg_start_ns, trigger = filtered_cuts[idx]
        seg_end_ns = filtered_cuts[idx + 1][0]
        dur_ms = (seg_end_ns - seg_start_ns) / 1_000_000.0

        # Find items strictly within this segment interval
        seg_events = [e for e in events if seg_start_ns <= e.relative_time_ns < seg_end_ns]
        if idx == len(filtered_cuts) - 2:  # Last segment includes end edge
            seg_events = [e for e in events if seg_start_ns <= e.relative_time_ns <= seg_end_ns]

        seg_frames = [
            f for f in frames
            if seg_start_ns <= int(f.get("monotonic_timestamp", 0.0) * 1_000_000_000) <= seg_end_ns
        ]
        seg_speech = [
            s for s in speech_segments
            if s.get("start_monotonic_ns", 0) <= seg_end_ns and s.get("end_monotonic_ns", 0) >= seg_start_ns
        ]
        seg_ann = [
            a for a in annotations
            if a.get("start_monotonic_ns", 0) <= seg_end_ns and a.get("end_monotonic_ns", 0) >= seg_start_ns
        ]

        item_ids = [e.event_id for e in seg_events]
        item_ids.extend([f.get("frame_id", "") for f in seg_frames if f.get("frame_id")])
        item_ids.extend([s.get("segment_id", "") for s in seg_speech if s.get("segment_id")])
        item_ids.extend([a.get("annotation_id", "") for a in seg_ann if a.get("annotation_id")])

        # Calculate statistics
        mouse_count = sum(1 for e in seg_events if e.category.value == "POINTER")
        keyboard_count = sum(1 for e in seg_events if e.category.value == "KEYBOARD")
        window_count = sum(1 for e in seg_events if e.category.value == "WINDOW")
        apps = sorted(list({e.application for e in seg_events if e.application}))
        displays = sorted(list({e.display_id for e in seg_events if e.display_id}))

        dur_sec = max(0.001, dur_ms / 1000.0)
        activity_density = round(len(seg_events) / dur_sec, 2)

        stats = {
            "event_count": len(seg_events),
            "mouse_event_count": mouse_count,
            "keyboard_event_count": keyboard_count,
            "window_count": window_count,
            "frame_count": len(seg_frames),
            "speech_count": len(seg_speech),
            "annotation_count": len(seg_ann),
            "applications": apps,
            "displays": displays,
            "activity_density": activity_density,
        }

        seg_id = f"seg_{idx + 1:04d}"
        segments.append(
            DemonstrationSegment(
                segment_id=seg_id,
                sequence=idx + 1,
                start_monotonic_ns=seg_start_ns,
                end_monotonic_ns=seg_end_ns,
                start_relative_ms=round(seg_start_ns / 1_000_000.0, 2),
                end_relative_ms=round(seg_end_ns / 1_000_000.0, 2),
                duration_ms=round(dur_ms, 2),
                boundary_trigger=trigger,
                item_ids=item_ids,
                statistics=stats,
            )
        )

    return segments
