"""Tests for recorder event model, timestamps, sequence ordering, and serialization."""

import json

from teach_a_skill.recorder.events import Event, EventPriority, EventType


def test_event_creation_and_defaults():
    evt = Event.create(
        session_id="sess_abc",
        sequence_number=1,
        event_type=EventType.MOUSE_CLICK,
        source="mouse",
        payload={"x": 100.0, "y": 200.0, "button": "LEFT"},
    )

    assert evt.event_id.startswith("evt_")
    assert evt.session_id == "sess_abc"
    assert evt.sequence_number == 1
    assert evt.event_type == EventType.MOUSE_CLICK
    assert evt.priority == EventPriority.CRITICAL  # Click defaults to CRITICAL
    assert evt.source == "mouse"
    assert evt.payload["x"] == 100.0
    assert evt.payload["button"] == "LEFT"
    assert evt.monotonic_timestamp > 0.0
    assert "T" in evt.timestamp  # ISO 8601


def test_event_priority_defaults():
    # Mouse move -> MEDIUM
    evt_move = Event.create("s1", 1, EventType.MOUSE_MOVE, "mouse")
    assert evt_move.priority == EventPriority.MEDIUM

    # Window change -> HIGH
    evt_win = Event.create("s1", 2, EventType.WINDOW_FOCUS_CHANGED, "window")
    assert evt_win.priority == EventPriority.HIGH

    # Screenshot captured -> LOW
    evt_frame = Event.create("s1", 3, EventType.SCREENSHOT_CAPTURED, "screen")
    assert evt_frame.priority == EventPriority.LOW

    # Key down -> CRITICAL
    evt_key = Event.create("s1", 4, EventType.KEY_DOWN, "keyboard")
    assert evt_key.priority == EventPriority.CRITICAL


def test_event_serialization_roundtrip():
    evt = Event.create(
        session_id="sess_roundtrip",
        sequence_number=42,
        event_type=EventType.KEY_DOWN,
        source="keyboard",
        payload={"key": "c", "modifiers": ["cmd"], "is_shortcut": True},
        priority=EventPriority.CRITICAL,
    )

    raw_json = evt.to_json()
    assert isinstance(raw_json, str)

    parsed_dict = json.loads(raw_json)
    restored = Event.from_dict(parsed_dict)

    assert restored.event_id == evt.event_id
    assert restored.session_id == evt.session_id
    assert restored.sequence_number == 42
    assert restored.event_type == EventType.KEY_DOWN
    assert restored.priority == EventPriority.CRITICAL
    assert restored.payload == evt.payload
    assert restored.monotonic_timestamp == evt.monotonic_timestamp
