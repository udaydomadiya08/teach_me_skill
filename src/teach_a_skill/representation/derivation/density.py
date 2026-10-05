"""Deterministic activity density, summary metrics, and statistics calculator."""

from typing import Any

from teach_a_skill.representation.models import (
    CanonicalEvent,
    ClickInteraction,
    DemonstrationSegment,
    DemonstrationSummary,
    DoubleClickInteraction,
    DragSequence,
    IdleInterval,
    KeyboardShortcutSequence,
    PointerPath,
    TextInputSequence,
)


def calculate_demonstration_summary(
    canonical_events: list[CanonicalEvent],
    pointer_paths: list[PointerPath],
    clicks: list[ClickInteraction],
    double_clicks: list[DoubleClickInteraction],
    drags: list[DragSequence],
    shortcuts: list[KeyboardShortcutSequence],
    text_inputs: list[TextInputSequence],
    segments: list[DemonstrationSegment],
    idle_intervals: list[IdleInterval],
    speech_segments: list[dict[str, Any]],
    annotations: list[dict[str, Any]],
    frames: list[dict[str, Any]],
    total_duration_sec: float,
) -> DemonstrationSummary:
    """Compute deterministic summary statistics and activity density metrics."""
    dur_sec = max(0.001, total_duration_sec)

    # Category counts
    cat_counts: dict[str, int] = {}
    apps: set[str] = set()
    windows: set[str] = set()

    for ev in canonical_events:
        cat = ev.category.value
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
        if ev.application:
            apps.add(ev.application)
        if ev.window_title:
            windows.add(ev.window_title)

    # Idle time metrics
    idle_duration_sec = sum(idle.duration_ms for idle in idle_intervals) / 1000.0
    idle_ratio = min(1.0, max(0.0, idle_duration_sec / dur_sec))

    # Speech duration
    speech_duration_sec = sum(
        (s.get("end_monotonic_ns", 0) - s.get("start_monotonic_ns", 0)) / 1_000_000_000.0
        for s in speech_segments
    )

    # Overall activity density
    events_per_sec = len(canonical_events) / dur_sec

    return DemonstrationSummary(
        total_duration_sec=round(dur_sec, 2),
        total_canonical_events=len(canonical_events),
        events_by_category=cat_counts,
        total_pointer_paths=len(pointer_paths),
        total_click_interactions=len(clicks),
        total_double_clicks=len(double_clicks),
        total_drag_sequences=len(drags),
        total_keyboard_shortcuts=len(shortcuts),
        total_text_inputs=len(text_inputs),
        total_segments=len(segments),
        total_speech_segments=len(speech_segments),
        total_speech_duration_sec=round(speech_duration_sec, 2),
        total_annotations=len(annotations),
        total_frames=len(frames),
        distinct_applications=sorted(list(apps)),
        distinct_windows=sorted(list(windows)),
        idle_duration_sec=round(idle_duration_sec, 2),
        idle_ratio=round(idle_ratio, 3),
        activity_density_events_per_sec=round(events_per_sec, 2),
    )
