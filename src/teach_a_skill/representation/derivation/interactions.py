"""Deterministic derivation of physical pointer paths, clicks, drags, shortcuts, and text sequences.

Strictly physical and geometric; non-semantic.
"""

import math
from typing import Any, Optional

from teach_a_skill.representation.models import (
    ApplicationTransition,
    CanonicalEvent,
    CanonicalEventType,
    ClickInteraction,
    DoubleClickInteraction,
    DragSequence,
    IdleInterval,
    KeyboardShortcutSequence,
    PointerPath,
    TextInputSequence,
    WindowContextInterval,
)


def derive_click_interactions(
    events: list[CanonicalEvent],
    session_id: str,
    max_duration_ms: float = 600.0,
    max_displacement_pixels: float = 12.0,
) -> list[ClickInteraction]:
    """Pair consecutive POINTER_DOWN and POINTER_UP events into ClickInteractions."""
    clicks: list[ClickInteraction] = []
    down_stack: list[CanonicalEvent] = []

    for ev in events:
        if ev.canonical_event_type == CanonicalEventType.POINTER_DOWN:
            down_stack.append(ev)
        elif ev.canonical_event_type == CanonicalEventType.POINTER_UP:
            btn = ev.payload.get("button", "left")
            matching_idx = None
            for idx in range(len(down_stack) - 1, -1, -1):
                d = down_stack[idx]
                if d.payload.get("button", "left") == btn:
                    matching_idx = idx
                    break

            if matching_idx is not None:
                down_ev = down_stack.pop(matching_idx)
                dur_ms = (ev.monotonic_timestamp - down_ev.monotonic_timestamp) * 1000.0

                dx = (ev.raw_x or 0.0) - (down_ev.raw_x or 0.0)
                dy = (ev.raw_y or 0.0) - (down_ev.raw_y or 0.0)
                displacement = math.sqrt(dx * dx + dy * dy)

                if dur_ms <= max_duration_ms and displacement <= max_displacement_pixels:
                    click_id = f"click_{len(clicks) + 1:05d}"
                    clicks.append(
                        ClickInteraction(
                            interaction_id=click_id,
                            down_event_id=down_ev.event_id,
                            up_event_id=ev.event_id,
                            monotonic_timestamp_ns=ev.relative_time_ns,
                            relative_time_ms=ev.relative_time_ms,
                            button=btn,
                            raw_x=down_ev.raw_x or 0.0,
                            raw_y=down_ev.raw_y or 0.0,
                            normalized_x=down_ev.normalized_x,
                            normalized_y=down_ev.normalized_y,
                            display_id=down_ev.display_id,
                            duration_ms=round(dur_ms, 2),
                            provenance={
                                "source_session_id": session_id,
                                "down_source_id": down_ev.source_event_id,
                                "up_source_id": ev.source_event_id,
                            },
                        )
                    )

    return clicks


def derive_double_clicks(
    clicks: list[ClickInteraction],
    session_id: str,
    max_interval_ms: float = 400.0,
    max_displacement_pixels: float = 10.0,
) -> list[DoubleClickInteraction]:
    """Pair consecutive clicks into DoubleClickInteractions."""
    double_clicks: list[DoubleClickInteraction] = []
    i = 0
    while i < len(clicks) - 1:
        c1 = clicks[i]
        c2 = clicks[i + 1]

        dt = c2.relative_time_ms - c1.relative_time_ms
        dx = c2.raw_x - c1.raw_x
        dy = c2.raw_y - c1.raw_y
        dist = math.sqrt(dx * dx + dy * dy)

        if c1.button == c2.button and 0 <= dt <= max_interval_ms and dist <= max_displacement_pixels:
            dc_id = f"dblclick_{len(double_clicks) + 1:04d}"
            double_clicks.append(
                DoubleClickInteraction(
                    interaction_id=dc_id,
                    first_click_id=c1.interaction_id,
                    second_click_id=c2.interaction_id,
                    monotonic_timestamp_ns=c2.monotonic_timestamp_ns,
                    relative_time_ms=c2.relative_time_ms,
                    button=c1.button,
                    raw_x=c1.raw_x,
                    raw_y=c1.raw_y,
                    interval_ms=round(dt, 2),
                    provenance={"source_session_id": session_id},
                )
            )
            i += 2
        else:
            i += 1

    return double_clicks


def derive_drag_sequences(
    events: list[CanonicalEvent],
    session_id: str,
    min_drag_distance_pixels: float = 15.0,
) -> list[DragSequence]:
    """Derive physical drag sequences from pointer down, moves, and pointer up."""
    drags: list[DragSequence] = []
    active_down: Optional[CanonicalEvent] = None
    moves_in_drag: list[CanonicalEvent] = []

    for ev in events:
        if ev.canonical_event_type == CanonicalEventType.POINTER_DOWN:
            active_down = ev
            moves_in_drag = []
        elif ev.canonical_event_type == CanonicalEventType.POINTER_MOVE:
            if active_down is not None:
                moves_in_drag.append(ev)
        elif ev.canonical_event_type == CanonicalEventType.POINTER_UP:
            if active_down is not None:
                start_x = active_down.raw_x or 0.0
                start_y = active_down.raw_y or 0.0
                end_x = ev.raw_x or (moves_in_drag[-1].raw_x if moves_in_drag else start_x) or 0.0
                end_y = ev.raw_y or (moves_in_drag[-1].raw_y if moves_in_drag else start_y) or 0.0

                dx = end_x - start_x
                dy = end_y - start_y
                dist = math.sqrt(dx * dx + dy * dy)

                if dist >= min_drag_distance_pixels and len(moves_in_drag) >= 1:
                    dur_ms = (ev.monotonic_timestamp - active_down.monotonic_timestamp) * 1000.0
                    drag_id = f"drag_{len(drags) + 1:04d}"
                    drags.append(
                        DragSequence(
                            sequence_id=drag_id,
                            down_event_id=active_down.event_id,
                            up_event_id=ev.event_id,
                            movement_event_ids=[m.event_id for m in moves_in_drag],
                            start_position=(round(start_x, 1), round(start_y, 1)),
                            end_position=(round(end_x, 1), round(end_y, 1)),
                            start_monotonic_ns=active_down.relative_time_ns,
                            end_monotonic_ns=ev.relative_time_ns,
                            duration_ms=round(dur_ms, 2),
                            display_id=active_down.display_id,
                            distance_pixels=round(dist, 2),
                            provenance={
                                "source_session_id": session_id,
                                "move_count": len(moves_in_drag),
                            },
                        )
                    )
                active_down = None
                moves_in_drag = []

    return drags


def derive_pointer_paths(
    events: list[CanonicalEvent],
    session_id: str,
    max_idle_gap_ms: float = 300.0,
) -> list[PointerPath]:
    """Group continuous pointer movements into pointer paths."""
    paths: list[PointerPath] = []
    current_moves: list[CanonicalEvent] = []

    def flush_path() -> None:
        if len(current_moves) < 2:
            current_moves.clear()
            return

        p0 = current_moves[0]
        pN = current_moves[-1]
        dur_ms = (pN.monotonic_timestamp - p0.monotonic_timestamp) * 1000.0

        pts: list[dict[str, Any]] = []
        total_dist = 0.0
        dir_changes = 0
        last_angle = None

        for idx, m in enumerate(current_moves):
            rx = m.raw_x or 0.0
            ry = m.raw_y or 0.0
            pts.append({
                "x": rx,
                "y": ry,
                "t_ms": round(m.relative_time_ms, 1),
            })
            if idx > 0:
                px = current_moves[idx - 1].raw_x or 0.0
                py = current_moves[idx - 1].raw_y or 0.0
                step_dx = rx - px
                step_dy = ry - py
                total_dist += math.sqrt(step_dx * step_dx + step_dy * step_dy)

                curr_angle = math.atan2(step_dy, step_dx)
                if last_angle is not None:
                    d_theta = abs(curr_angle - last_angle)
                    if d_theta > math.pi / 4.0:  # > 45 deg change
                        dir_changes += 1
                last_angle = curr_angle

        path_id = f"path_{len(paths) + 1:05d}"
        paths.append(
            PointerPath(
                path_id=path_id,
                start_event_id=p0.event_id,
                end_event_id=pN.event_id,
                start_monotonic_ns=p0.relative_time_ns,
                end_monotonic_ns=pN.relative_time_ns,
                duration_ms=round(dur_ms, 2),
                display_id=p0.display_id,
                points=pts,
                distance_pixels=round(total_dist, 2),
                direction_changes=dir_changes,
                provenance={"source_session_id": session_id},
            )
        )
        current_moves.clear()

    for ev in events:
        if ev.canonical_event_type == CanonicalEventType.POINTER_MOVE:
            if current_moves:
                gap = (ev.monotonic_timestamp - current_moves[-1].monotonic_timestamp) * 1000.0
                if gap > max_idle_gap_ms:
                    flush_path()
            current_moves.append(ev)
        elif ev.canonical_event_type in (
            CanonicalEventType.POINTER_DOWN,
            CanonicalEventType.POINTER_UP,
            CanonicalEventType.CLICK,
        ):
            flush_path()

    flush_path()
    return paths


def derive_keyboard_shortcuts(
    events: list[CanonicalEvent],
    session_id: str,
) -> list[KeyboardShortcutSequence]:
    """Derive physical keyboard shortcut sequences without semantic interpretation."""
    shortcuts: list[KeyboardShortcutSequence] = []
    active_modifiers: dict[str, CanonicalEvent] = {}

    MOD_KEYS = {"control", "shift", "alt", "meta", "command", "ctrl", "option"}

    for ev in events:
        if ev.canonical_event_type == CanonicalEventType.KEY_DOWN:
            key_name = str(ev.payload.get("key", ""))
            is_mod = bool(ev.payload.get("is_modifier", False)) or (key_name.lower() in MOD_KEYS)
            if is_mod:
                active_modifiers[key_name] = ev
            elif active_modifiers and key_name:
                # Modifiers held + regular key down = physical shortcut
                all_ev_ids = [m.event_id for m in active_modifiers.values()] + [ev.event_id]
                t_start = min(m.monotonic_timestamp for m in active_modifiers.values())
                dur_ms = max(0.0, (ev.monotonic_timestamp - t_start) * 1000.0)

                seq_id = f"shortcut_{len(shortcuts) + 1:04d}"
                mod_names = sorted(list(active_modifiers.keys()))
                shortcuts.append(
                    KeyboardShortcutSequence(
                        sequence_id=seq_id,
                        event_ids=all_ev_ids,
                        modifiers=mod_names,
                        key=key_name,
                        keys=[key_name],
                        monotonic_timestamp_ns=ev.relative_time_ns,
                        relative_time_ms=ev.relative_time_ms,
                        duration_ms=round(dur_ms, 2),
                        provenance={
                            "source_session_id": session_id,
                            "physical_key_combination": "+".join(mod_names + [key_name]),
                        },
                    )
                )
        elif ev.canonical_event_type == CanonicalEventType.KEY_UP:
            key_name = str(ev.payload.get("key", ""))
            # Remove from active_modifiers (case-insensitive match)
            to_remove = [k for k in active_modifiers if k.lower() == key_name.lower()]
            for k in to_remove:
                active_modifiers.pop(k, None)

    return shortcuts


def derive_text_input_sequences(
    events: list[CanonicalEvent],
    session_id: str,
    max_keystroke_gap_ms: float = 1200.0,
) -> list[TextInputSequence]:
    """Group sequential text entries into privacy-preserving sequences (counts only)."""
    sequences: list[TextInputSequence] = []
    current_burst: list[CanonicalEvent] = []

    def flush_burst() -> None:
        if not current_burst:
            return
        e0 = current_burst[0]
        eN = current_burst[-1]
        dur_ms = (eN.monotonic_timestamp - e0.monotonic_timestamp) * 1000.0

        # Calculate character count safely without logging raw secret contents
        char_count = sum(len(str(ev.payload.get("text", ev.payload.get("key", " ")))) for ev in current_burst)

        seq_id = f"text_seq_{len(sequences) + 1:04d}"
        sequences.append(
            TextInputSequence(
                sequence_id=seq_id,
                event_ids=[ev.event_id for ev in current_burst],
                character_count=char_count,
                text_length=char_count,
                application=e0.application,
                window_title=e0.window_title,
                start_monotonic_ns=e0.relative_time_ns,
                end_monotonic_ns=eN.relative_time_ns,
                duration_ms=round(dur_ms, 2),
                provenance={"source_session_id": session_id},
            )
        )
        current_burst.clear()

    active_modifiers: set[str] = set()
    MOD_KEYS = {"control", "shift", "alt", "meta", "command", "ctrl", "option"}
    NON_TEXT_MODIFIERS = {"control", "alt", "meta", "command", "ctrl", "option"}

    for ev in events:
        key_name = str(ev.payload.get("key", "")).lower()
        is_mod = bool(ev.payload.get("is_modifier", False)) or (key_name in MOD_KEYS)

        if ev.canonical_event_type == CanonicalEventType.KEY_DOWN and is_mod:
            active_modifiers.add(key_name)
        elif ev.canonical_event_type == CanonicalEventType.KEY_UP and is_mod:
            active_modifiers.discard(key_name)

        has_non_text_mod = any(m in NON_TEXT_MODIFIERS for m in active_modifiers)

        is_text_event = (not has_non_text_mod) and (
            ev.canonical_event_type == CanonicalEventType.TEXT_INPUT
            or (
                ev.canonical_event_type == CanonicalEventType.KEY_DOWN
                and len(ev.payload.get("key", "")) == 1
                and not is_mod
                and not ev.payload.get("modifiers")
            )
        )

        if is_text_event:
            if current_burst:
                gap = (ev.monotonic_timestamp - current_burst[-1].monotonic_timestamp) * 1000.0
                if gap > max_keystroke_gap_ms or ev.application != current_burst[0].application:
                    flush_burst()
            current_burst.append(ev)
        elif ev.canonical_event_type in (
            CanonicalEventType.POINTER_DOWN,
            CanonicalEventType.CLICK,
            CanonicalEventType.WINDOW_FOCUS,
        ):
            flush_burst()

    flush_burst()
    return sequences


def derive_idle_intervals(
    events: list[CanonicalEvent],
    session_duration_sec: float,
    threshold_sec: float = 3.0,
) -> list[IdleInterval]:
    """Detect inactivity intervals greater than threshold."""
    idles: list[IdleInterval] = []
    threshold_ns = int(threshold_sec * 1_000_000_000)

    if not events:
        if session_duration_sec > threshold_sec:
            idles.append(
                IdleInterval(
                    interval_id="idle_0001",
                    start_monotonic_ns=0,
                    end_monotonic_ns=int(session_duration_sec * 1_000_000_000),
                    duration_ms=round(session_duration_sec * 1000.0, 2),
                )
            )
        return idles

    for i in range(len(events) - 1):
        e1 = events[i]
        e2 = events[i + 1]
        gap_ns = e2.relative_time_ns - e1.relative_time_ns
        if gap_ns >= threshold_ns:
            dur_ms = (e2.monotonic_timestamp - e1.monotonic_timestamp) * 1000.0
            idles.append(
                IdleInterval(
                    interval_id=f"idle_{len(idles) + 1:04d}",
                    start_monotonic_ns=e1.relative_time_ns,
                    end_monotonic_ns=e2.relative_time_ns,
                    duration_ms=round(dur_ms, 2),
                    preceding_event_id=e1.event_id,
                    succeeding_event_id=e2.event_id,
                )
            )

    return idles


def derive_window_context_intervals(
    events: list[CanonicalEvent],
    session_id: str,
) -> list[WindowContextInterval]:
    """Create continuous intervals of active window and application context."""
    intervals: list[WindowContextInterval] = []
    window_events = [e for e in events if e.canonical_event_type == CanonicalEventType.WINDOW_FOCUS]

    if not window_events:
        return intervals

    for i, wev in enumerate(window_events):
        app = wev.application or wev.payload.get("app_name", "Unknown")
        title = wev.window_title or wev.payload.get("title", "Unknown")
        pid = wev.process_id or wev.payload.get("process_id")

        start_ns = wev.relative_time_ns
        if i < len(window_events) - 1:
            end_ns = window_events[i + 1].relative_time_ns
            dur_ms = (window_events[i + 1].monotonic_timestamp - wev.monotonic_timestamp) * 1000.0
        else:
            end_ns = events[-1].relative_time_ns if events else start_ns
            dur_ms = (events[-1].monotonic_timestamp - wev.monotonic_timestamp) * 1000.0 if events else 0.0

        intervals.append(
            WindowContextInterval(
                interval_id=f"win_ctx_{len(intervals) + 1:04d}",
                application=app,
                window_title=title,
                process_id=pid,
                start_monotonic_ns=start_ns,
                end_monotonic_ns=max(start_ns, end_ns),
                duration_ms=max(0.0, round(dur_ms, 2)),
                focus_event_id=wev.event_id,
            )
        )

    return intervals


def derive_application_transitions(
    events: list[CanonicalEvent],
    session_id: str,
) -> list[ApplicationTransition]:
    """Derive application switch milestones from window focus events."""
    transitions: list[ApplicationTransition] = []
    window_events = [e for e in events if e.canonical_event_type == CanonicalEventType.WINDOW_FOCUS]

    last_app: Optional[str] = None
    for wev in window_events:
        app = wev.application or wev.payload.get("app_name", "Unknown")
        if app != last_app and app != "Unknown":
            t_id = f"app_trans_{len(transitions) + 1:04d}"
            transitions.append(
                ApplicationTransition(
                    transition_id=t_id,
                    from_application=last_app,
                    to_application=app,
                    event_id=wev.event_id,
                    monotonic_timestamp_ns=wev.relative_time_ns,
                    relative_time_ms=wev.relative_time_ms,
                )
            )
            last_app = app

    return transitions
