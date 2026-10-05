"""Configuration manager with loading, validation, and migration support."""

import json
try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]
from pathlib import Path
from typing import Any, Optional

from teach_a_skill.config.defaults import get_default_config
from teach_a_skill.config.schema import (
    AppConfig,
    LoggingConfig,
    ModelsConfig,
    PerformanceConfig,
    PrivacyConfig,
    RecordingSettingsConfig,
    StorageConfig,
)
from teach_a_skill.core.errors import ConfigurationError
from teach_a_skill.privacy.policy import PrivacyPolicy


class ConfigManager:
    """Manages reading, validating, writing, and migrating local configuration."""

    VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    VALID_TIERS = {None, "BASELINE", "STANDARD", "HIGH"}
    VALID_PERF_MODES = {"automatic", "conservative", "performance"}

    def __init__(self, config_path: Optional[Path] = None) -> None:
        self.config_path = config_path
        self._config: Optional[AppConfig] = None

    def get_config(self) -> AppConfig:
        """Return the current configuration, loading default if not loaded."""
        if self._config is None:
            if self.config_path and self.config_path.exists():
                self._config = self.load(self.config_path)
            else:
                self._config = get_default_config()
        return self._config

    def set_config(self, config: AppConfig) -> None:
        """Validate and set active configuration."""
        self.validate(config)
        self._config = config

    def validate(self, config: AppConfig) -> None:
        """Validate configuration values against constraints."""
        if config.logging.level.upper() not in self.VALID_LOG_LEVELS:
            raise ConfigurationError(
                f"Invalid log level '{config.logging.level}'. Must be one of {self.VALID_LOG_LEVELS}"
            )

        if config.performance.tier_override not in self.VALID_TIERS:
            raise ConfigurationError(
                f"Invalid tier override '{config.performance.tier_override}'. Must be one of {self.VALID_TIERS}"
            )

        if config.performance.mode not in self.VALID_PERF_MODES:
            raise ConfigurationError(
                f"Invalid performance mode '{config.performance.mode}'. Must be one of {self.VALID_PERF_MODES}"
            )

        if config.recording.fps <= 0 or config.recording.fps > 60:
            raise ConfigurationError(
                f"Recording FPS must be between 1 and 60, got {config.recording.fps}"
            )

        if config.storage.retention_days < 1:
            raise ConfigurationError(
                f"Retention days must be at least 1, got {config.storage.retention_days}"
            )

    def load(self, path: Path) -> AppConfig:
        """Load configuration from a JSON or TOML file."""
        if not path.exists():
            raise ConfigurationError(f"Config file not found: {path}")

        try:
            content = path.read_text(encoding="utf-8")
            if path.suffix.lower() == ".toml":
                raw_dict = tomllib.loads(content)
            else:
                raw_dict = json.loads(content)
        except Exception as e:
            raise ConfigurationError(f"Failed to parse config file '{path}': {e}") from e

        migrated_dict = self.migrate(raw_dict)
        config = self._from_dict(migrated_dict)
        self.validate(config)
        self._config = config
        return config

    def migrate(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Apply schema migrations across version upgrades."""
        version = raw.get("version", 1)
        if version == 1:
            return raw

        # Future migrations would step through versions:
        # if version < 2:
        #     raw = self._migrate_v1_to_v2(raw)
        return raw

    def save_json(self, target_path: Path) -> None:
        """Save active configuration as JSON."""
        config = self.get_config()
        self.validate(config)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write
        temp_path = target_path.with_suffix(f"{target_path.suffix}.tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(config.to_dict(), f, indent=2)
            temp_path.replace(target_path)
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            raise ConfigurationError(f"Failed to save configuration to '{target_path}': {e}") from e

    def get_privacy_policy(self) -> PrivacyPolicy:
        """Derive an active IPrivacyPolicy instance from current configuration."""
        cfg = self.get_config().privacy
        return PrivacyPolicy(
            _local_only=cfg.local_only,
            _allow_network=cfg.allow_network,
            _telemetry_enabled=cfg.telemetry,
            _cloud_inference_enabled=cfg.cloud_inference,
            _data_upload_enabled=False,  # Hard locked in Phase 1
            _persist_user_content=True,
            _screen_capture_allowed=False,
            _microphone_allowed=False,
            _redact_logs=cfg.redact_logs,
        )

    def _from_dict(self, data: dict[str, Any]) -> AppConfig:
        """Hydrate AppConfig from parsed dictionary."""
        priv_d = data.get("privacy", {})
        perf_d = data.get("performance", {})
        mod_d = data.get("models", {})
        rec_d = data.get("recording", {})
        stor_d = data.get("storage", {})
        log_d = data.get("logging", {})

        return AppConfig(
            version=data.get("version", 1),
            privacy=PrivacyConfig(**priv_d),
            performance=PerformanceConfig(**perf_d),
            models=ModelsConfig(**mod_d),
            recording=RecordingSettingsConfig(**rec_d),
            storage=StorageConfig(**stor_d),
            logging=LoggingConfig(**log_d),
        )
