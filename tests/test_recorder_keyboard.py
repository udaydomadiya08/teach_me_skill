"""Tests for keyboard events and shortcut reconstruction."""

from teach_a_skill.recorder.keyboard import (
    KeyAction,
    KeyEventPayload,
    ShortcutReconstructor,
)


def test_keyboard_payload_serialization():
    payload = KeyEventPayload(
        key="Return",
        action=KeyAction.DOWN,
        modifiers=["ctrl"],
        is_shortcut=True,
        shortcut_string="Ctrl+Return",
    )
    p_dict = payload.to_dict()
    assert p_dict["key"] == "Return"
    assert p_dict["action"] == "DOWN"
    assert p_dict["modifiers"] == ["ctrl"]
    assert p_dict["is_shortcut"] is True
    assert p_dict["shortcut_string"] == "Ctrl+Return"


def test_shortcut_reconstructor_cmd_c():
    reconstructor = ShortcutReconstructor()

    # Press Command key
    p1 = reconstructor.process_key_event("Command", KeyAction.DOWN)
    assert p1.modifiers == ["cmd"]
    assert p1.is_shortcut is False  # Modifier alone is not a shortcut

    # Press 'c' while Command is held
    p2 = reconstructor.process_key_event("c", KeyAction.DOWN)
    assert p2.modifiers == ["cmd"]
    assert p2.is_shortcut is True
    assert p2.shortcut_string == "Cmd+C"

    # Release 'c'
    p3 = reconstructor.process_key_event("c", KeyAction.UP)
    assert p3.is_shortcut is False

    # Release Command
    p4 = reconstructor.process_key_event("Command", KeyAction.UP)
    assert p4.modifiers == []


def test_shortcut_reconstructor_multi_modifier():
    reconstructor = ShortcutReconstructor()

    # Ctrl + Shift + P
    reconstructor.process_key_event("Control", KeyAction.DOWN)
    reconstructor.process_key_event("Shift", KeyAction.DOWN)
    payload = reconstructor.process_key_event("p", KeyAction.DOWN)

    assert payload.is_shortcut is True
    assert "Ctrl" in payload.shortcut_string
    assert "Shift" in payload.shortcut_string
    assert "P" in payload.shortcut_string

    reconstructor.reset()
    assert reconstructor._active_modifiers == set()
