"""Tests for privacy policy and runtime enforcement."""

import pytest

from teach_a_skill.core.errors import PrivacyViolationError
from teach_a_skill.privacy.guard import PrivacyGuard
from teach_a_skill.privacy.policy import PrivacyPolicy


def test_default_privacy_policy_invariants():
    policy = PrivacyPolicy.default()
    assert policy.local_only is True
    assert policy.allow_network is False
    assert policy.telemetry_enabled is False
    assert policy.cloud_inference_enabled is False
    assert policy.data_upload_enabled is False
    assert policy.persist_user_content is True
    assert policy.screen_capture_allowed is False
    assert policy.microphone_allowed is False
    assert policy.redact_logs is True


def test_guard_blocks_network_by_default():
    guard = PrivacyGuard(PrivacyPolicy.default())
    with pytest.raises(PrivacyViolationError, match="Network access is prohibited"):
        guard.assert_network_allowed("https://api.openai.com/v1/chat")


def test_guard_blocks_telemetry():
    guard = PrivacyGuard(PrivacyPolicy.default())
    with pytest.raises(PrivacyViolationError, match="Telemetry collection is disabled"):
        guard.assert_telemetry_allowed()


def test_guard_blocks_cloud_inference():
    guard = PrivacyGuard(PrivacyPolicy.default())
    with pytest.raises(PrivacyViolationError, match="Cloud inference is disabled"):
        guard.assert_cloud_inference_allowed()


def test_guard_blocks_unpermitted_screen_capture():
    guard = PrivacyGuard(PrivacyPolicy.default())
    with pytest.raises(PrivacyViolationError, match="Screen capture is disabled"):
        guard.assert_screen_capture_allowed()


def test_guard_blocks_unpermitted_microphone_access():
    guard = PrivacyGuard(PrivacyPolicy.default())
    with pytest.raises(PrivacyViolationError, match="Microphone access is disabled"):
        guard.assert_microphone_allowed()


def test_policy_serialization():
    policy = PrivacyPolicy.default()
    p_dict = policy.to_dict()
    assert p_dict["local_only"] is True
    assert p_dict["allow_network"] is False
    assert p_dict["telemetry_enabled"] is False
