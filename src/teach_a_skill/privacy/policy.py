"""Privacy policy specification and configuration."""

from dataclasses import dataclass
from typing import Any

from teach_a_skill.interfaces.privacy import IPrivacyPolicy


@dataclass(frozen=True)
class PrivacyPolicy(IPrivacyPolicy):
    """Enforceable privacy policy defining operational permissions."""

    _local_only: bool = True
    _allow_network: bool = False
    _telemetry_enabled: bool = False
    _cloud_inference_enabled: bool = False
    _data_upload_enabled: bool = False
    _persist_user_content: bool = True  # Allowed to persist locally on user's disk
    _screen_capture_allowed: bool = False  # Disabled by default until explicit session in Phase 2
    _microphone_allowed: bool = False  # Disabled by default until explicit session in Phase 3
    _redact_logs: bool = True

    @property
    def local_only(self) -> bool:
        return self._local_only

    @property
    def allow_network(self) -> bool:
        return self._allow_network

    @property
    def telemetry_enabled(self) -> bool:
        return self._telemetry_enabled

    @property
    def cloud_inference_enabled(self) -> bool:
        return self._cloud_inference_enabled

    @property
    def data_upload_enabled(self) -> bool:
        return self._data_upload_enabled

    @property
    def persist_user_content(self) -> bool:
        return self._persist_user_content

    @property
    def screen_capture_allowed(self) -> bool:
        return self._screen_capture_allowed

    @property
    def microphone_allowed(self) -> bool:
        return self._microphone_allowed

    @property
    def redact_logs(self) -> bool:
        return self._redact_logs

    def to_dict(self) -> dict[str, Any]:
        """Convert policy to clean dictionary."""
        return {
            "local_only": self.local_only,
            "allow_network": self.allow_network,
            "telemetry_enabled": self.telemetry_enabled,
            "cloud_inference_enabled": self.cloud_inference_enabled,
            "data_upload_enabled": self.data_upload_enabled,
            "persist_user_content": self.persist_user_content,
            "screen_capture_allowed": self.screen_capture_allowed,
            "microphone_allowed": self.microphone_allowed,
            "redact_logs": self.redact_logs,
        }

    @classmethod
    def default(cls) -> "PrivacyPolicy":
        """Return the strict zero-leak default privacy policy."""
        return cls()
