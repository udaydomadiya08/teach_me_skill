"""Default configuration factory."""

from teach_a_skill.config.schema import (
    AppConfig,
    LoggingConfig,
    ModelsConfig,
    PerformanceConfig,
    PrivacyConfig,
    RecordingSettingsConfig,
    StorageConfig,
)
from teach_a_skill.platform import get_platform_adapter


def get_default_config() -> AppConfig:
    """Generate default configuration populated with platform-appropriate storage paths."""
    platform_adapter = get_platform_adapter()
    default_dir = platform_adapter.get_default_data_dir()

    return AppConfig(
        version=1,
        privacy=PrivacyConfig(
            local_only=True,
            telemetry=False,
            cloud_inference=False,
            allow_network=False,
            redact_logs=True,
        ),
        performance=PerformanceConfig(
            mode="automatic",
            tier_override=None,
            power_mode="automatic",
            max_memory_mb=None,
        ),
        models=ModelsConfig(
            selection="automatic",
            local_models_dir="models",
            default_vision_model=None,
            default_speech_model=None,
            default_ocr_model=None,
        ),
        recording=RecordingSettingsConfig(
            fps=10,
            capture_audio=False,
            record_mouse_clicks=True,
            record_keystrokes=True,
            screen_resolution_scale=1.0,
        ),
        storage=StorageConfig(
            data_directory=default_dir,
            retention_days=30,
            max_storage_gb=50,
        ),
        logging=LoggingConfig(
            level="INFO",
            json_format=False,
            log_to_file=True,
        ),
    )
