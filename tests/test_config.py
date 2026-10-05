"""Tests for configuration management."""

import pytest

from teach_a_skill.config.defaults import get_default_config
from teach_a_skill.config.manager import ConfigManager
from teach_a_skill.core.errors import ConfigurationError


def test_default_config_invariants():
    """Verify default configuration strictly enforces local-only privacy."""
    cfg = get_default_config()
    assert cfg.version == 1
    assert cfg.privacy.local_only is True
    assert cfg.privacy.telemetry is False
    assert cfg.privacy.cloud_inference is False
    assert cfg.privacy.allow_network is False
    assert cfg.performance.mode == "automatic"
    assert cfg.recording.fps == 10
    assert cfg.storage.retention_days == 30


def test_config_validation_invalid_log_level():
    mgr = ConfigManager()
    cfg = get_default_config()
    cfg.logging.level = "INVALID_LEVEL"
    with pytest.raises(ConfigurationError, match="Invalid log level"):
        mgr.validate(cfg)


def test_config_validation_invalid_fps():
    mgr = ConfigManager()
    cfg = get_default_config()
    cfg.recording.fps = 120  # Exceeds max allowed
    with pytest.raises(ConfigurationError, match="Recording FPS must be between 1 and 60"):
        mgr.validate(cfg)


def test_config_validation_invalid_tier_override():
    mgr = ConfigManager()
    cfg = get_default_config()
    cfg.performance.tier_override = "SUPER_ULTRA"
    with pytest.raises(ConfigurationError, match="Invalid tier override"):
        mgr.validate(cfg)


def test_save_and_load_json(temp_dir):
    cfg_file = temp_dir / "custom_config.json"
    mgr = ConfigManager(cfg_file)
    cfg = get_default_config()
    cfg.logging.level = "DEBUG"
    cfg.performance.tier_override = "STANDARD"

    mgr.set_config(cfg)
    mgr.save_json(cfg_file)

    assert cfg_file.exists()

    # Load in new manager
    new_mgr = ConfigManager(cfg_file)
    loaded_cfg = new_mgr.get_config()

    assert loaded_cfg.logging.level == "DEBUG"
    assert loaded_cfg.performance.tier_override == "STANDARD"
    assert loaded_cfg.privacy.local_only is True


def test_load_toml_config(temp_dir):
    toml_file = temp_dir / "config.toml"
    toml_content = """
    version = 1

    [privacy]
    local_only = true
    telemetry = false
    cloud_inference = false
    allow_network = false
    redact_logs = true

    [performance]
    mode = "conservative"
    power_mode = "balanced"

    [logging]
    level = "WARNING"
    json_format = true
    log_to_file = false
    """
    toml_file.write_text(toml_content, encoding="utf-8")

    mgr = ConfigManager(toml_file)
    cfg = mgr.get_config()

    assert cfg.performance.mode == "conservative"
    assert cfg.logging.level == "WARNING"
    assert cfg.logging.json_format is True
    assert cfg.privacy.local_only is True


def test_config_migration():
    mgr = ConfigManager()
    raw = {"version": 1, "privacy": {"local_only": True}}
    migrated = mgr.migrate(raw)
    assert migrated["version"] == 1
