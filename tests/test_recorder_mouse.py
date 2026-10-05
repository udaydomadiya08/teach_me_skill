"""Tests for mouse events and movement coalescing engine."""

from teach_a_skill.recorder.mouse import (
    MouseAction,
    MouseButton,
    MouseEventPayload,
    MovementCoalescer,
)


def test_mouse_payload_serialization():
    payload = MouseEventPayload(
        x=500.5,
        y=320.0,
        action=MouseAction.CLICK,
        button=MouseButton.LEFT,
        display_id=1,
        scale_factor=2.0,
        modifiers=["shift"],
    )
    p_dict = payload.to_dict()
    assert p_dict["x"] == 500.5
    assert p_dict["y"] == 320.0
    assert p_dict["action"] == "CLICK"
    assert p_dict["button"] == "LEFT"
    assert p_dict["modifiers"] == ["shift"]


def test_coalescer_filters_micro_jitter():
    coalescer = MovementCoalescer(min_distance_px=10.0, min_interval_sec=0.05)

    # First point: always emitted
    t0 = 100.0
    assert coalescer.should_emit_movement(100.0, 100.0, now_mono=t0) is True

    # Micro jitter (+2px, within interval): dropped
    assert coalescer.should_emit_movement(102.0, 101.0, now_mono=t0 + 0.01) is False

    # Still too close (+5px total): dropped
    assert coalescer.should_emit_movement(104.0, 103.0, now_mono=t0 + 0.02) is False

    # Significant movement (+30px and time passed): emitted
    assert coalescer.should_emit_movement(130.0, 100.0, now_mono=t0 + 0.06) is True


def test_coalescer_preserves_directional_inflections():
    coalescer = MovementCoalescer(
        min_distance_px=10.0, min_interval_sec=0.1, direction_threshold_rad=0.3
    )

    t0 = 100.0
    assert coalescer.should_emit_movement(0.0, 0.0, now_mono=t0) is True
    # Moving along +X axis
    assert coalescer.should_emit_movement(50.0, 0.0, now_mono=t0 + 0.15) is True

    # Sharp 90-degree turn along +Y axis shortly after (< min_interval, but sharp angle): emitted
    assert coalescer.should_emit_movement(50.0, 40.0, now_mono=t0 + 0.17) is True


def test_coalescer_drag_preservation():
    coalescer = MovementCoalescer(min_distance_px=10.0, min_interval_sec=0.05)

    t = 200.0
    # Button down at start
    coalescer.notify_button_state(MouseButton.LEFT, is_down=True, x=100.0, y=100.0, now_mono=t)

    # In drag mode, sensitivity increases (lower min distance threshold)
    # min_distance is 10.0 * 0.5 = 5.0, distance is 6.0, dt is 0.04 > effective_min_interval (0.05 * 0.6 = 0.03)
    assert coalescer.should_emit_movement(106.0, 100.0, now_mono=t + 0.04) is True

    # Flush final point on release
    coalescer.notify_button_state(MouseButton.LEFT, is_down=False, x=150.0, y=100.0)
    flushed = coalescer.flush_final_point(155.0, 100.0)
    assert flushed is True
