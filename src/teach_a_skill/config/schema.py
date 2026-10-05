"""Configuration schemas for Teach A Skill."""

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass
class PrivacyConfig:
    local_only: bool = True
    telemetry: bool = False
    cloud_inference: bool = False
    allow_network: bool = False
    redact_logs: bool = True


@dataclass
class PerformanceConfig:
    mode: str = "automatic"  # "automatic", "conservative", "performance"
    tier_override: Optional[str] = None  # None, "BASELINE", "STANDARD", "HIGH"
    power_mode: str = "automatic"  # "automatic", "balanced", "low_power"
    max_memory_mb: Optional[int] = None  # Explicit cap, or None to use budget


@dataclass
class ModelsConfig:
    selection: str = "automatic"
    local_models_dir: str = "models"
    default_vision_model: Optional[str] = None
    default_speech_model: Optional[str] = None
    default_ocr_model: Optional[str] = None


@dataclass
class RecordingSettingsConfig:
    fps: int = 10
    capture_audio: bool = False
    record_mouse_clicks: bool = True
    record_keystrokes: bool = True
    screen_resolution_scale: float = 1.0


@dataclass
class StorageConfig:
    data_directory: str = ""  # Populated with platform default if blank
    retention_days: int = 30
    max_storage_gb: int = 50


@dataclass
class LoggingConfig:
    level: str = "INFO"
    json_format: bool = False
    log_to_file: bool = True


@dataclass
class AppConfig:
    """Master application configuration container."""

    version: int = 1
    privacy: PrivacyConfig = field(default_factory=PrivacyConfig)
    performance: PerformanceConfig = field(default_factory=PerformanceConfig)
    models: ModelsConfig = field(default_factory=ModelsConfig)
    recording: RecordingSettingsConfig = field(default_factory=RecordingSettingsConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary."""
        return asdict(self)
