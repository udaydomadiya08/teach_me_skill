"""Tests for sensitive input filtering and privacy barriers."""

from teach_a_skill.recorder.keyboard import KeyAction, KeyEventPayload
from teach_a_skill.recorder.sensitive import PrivacyFilter, SensitiveInputPolicy


def test_privacy_filter_record_normal():
    filter_engine = PrivacyFilter(input_policy=SensitiveInputPolicy.RECORD)
    payload = KeyEventPayload(key="a", action=KeyAction.DOWN)

    filtered = filter_engine.filter_key_payload(
        payload, app_name="Visual Studio Code", window_title="main.py"
    )
    assert filtered is not None
    assert filtered.key == "a"


def test_privacy_filter_mask_policy():
    filter_engine = PrivacyFilter(input_policy=SensitiveInputPolicy.MASK)
    payload = KeyEventPayload(key="s", action=KeyAction.DOWN, text="s")

    filtered = filter_engine.filter_key_payload(payload, app_name="Terminal", window_title="bash")
    assert filtered is not None
    assert filtered.key == "*"
    assert filtered.text == "*"

    # Shortcuts must not be masked
    shortcut_payload = KeyEventPayload(
        key="c", action=KeyAction.DOWN, modifiers=["cmd"], is_shortcut=True, shortcut_string="Cmd+C"
    )
    shortcut_filtered = filter_engine.filter_key_payload(shortcut_payload)
    assert shortcut_filtered.key == "c"
    assert shortcut_filtered.shortcut_string == "Cmd+C"


def test_privacy_filter_suppress_policy():
    filter_engine = PrivacyFilter(input_policy=SensitiveInputPolicy.SUPPRESS)
    payload = KeyEventPayload(key="x", action=KeyAction.DOWN)

    filtered = filter_engine.filter_key_payload(payload, app_name="TextEdit")
    # Character key dropped completely
    assert filtered is None

    # Navigation keys preserved
    nav_payload = KeyEventPayload(key="Return", action=KeyAction.DOWN)
    nav_filtered = filter_engine.filter_key_payload(nav_payload, app_name="TextEdit")
    assert nav_filtered is not None
    assert nav_filtered.key == "Return"


def test_privacy_filter_app_exclusion():
    filter_engine = PrivacyFilter(input_policy=SensitiveInputPolicy.RECORD)

    # In 1Password, even under RECORD policy, input and screen capture are suppressed
    assert filter_engine.is_context_sensitive(app_name="1Password") is True
    assert filter_engine.should_suppress_screen_capture(app_name="1Password") is True

    payload = KeyEventPayload(key="p", action=KeyAction.DOWN)
    filtered = filter_engine.filter_key_payload(payload, app_name="1Password")
    assert filtered is None


def test_privacy_filter_window_regex_exclusion():
    filter_engine = PrivacyFilter(input_policy=SensitiveInputPolicy.RECORD)

    assert (
        filter_engine.is_context_sensitive(
            app_name="Chrome", window_title="Sign In - Account Password"
        )
        is True
    )
    assert (
        filter_engine.should_suppress_screen_capture(
            app_name="Chrome", window_title="Sign In - Account Password"
        )
        is True
    )

    payload = KeyEventPayload(key="1", action=KeyAction.DOWN)
    filtered = filter_engine.filter_key_payload(
        payload, app_name="Chrome", window_title="Enter master password"
    )
    assert filtered is None


def test_manual_privacy_mode():
    filter_engine = PrivacyFilter(input_policy=SensitiveInputPolicy.RECORD)
    assert (
        filter_engine.is_context_sensitive(app_name="Safari", window_title="Documentation") is False
    )

    filter_engine.set_manual_privacy_mode(True)
    assert (
        filter_engine.is_context_sensitive(app_name="Safari", window_title="Documentation") is True
    )
    assert filter_engine.should_suppress_screen_capture(app_name="Safari") is True
