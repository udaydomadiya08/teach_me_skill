"""Error hierarchy for the Teach A Skill system.

Provides structured, domain-specific exceptions.
"""

from typing import Any, Optional


class TeachSkillError(Exception):
    """Base exception for all domain errors within Teach A Skill."""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Convert error to a structured dictionary for safe diagnostic reporting."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "details": self.details,
        }


class ConfigurationError(TeachSkillError):
    """Raised when configuration is invalid, unreadable, or violates constraints."""


class HardwareDetectionError(TeachSkillError):
    """Raised when hardware detection fails unexpectedly."""


class StorageError(TeachSkillError):
    """Base exception for storage and filesystem failures."""


class StoragePathTraversalError(StorageError):
    """Raised when a path attempts to escape the designated storage sandbox."""


class StorageCorruptionError(StorageError):
    """Raised when stored data or metadata is corrupt or unparseable."""


class StoragePermissionError(StorageError):
    """Raised when storage locations lack required read/write permissions."""


class PrivacyViolationError(TeachSkillError):
    """Raised when an operation attempts to violate privacy boundaries.

    Examples: unauthorized network access, telemetry transmission, or unpermitted capture.
    """


class CapabilityUnavailableError(TeachSkillError):
    """Raised when an operation requires hardware or model capabilities not available."""


class ModelRegistryError(TeachSkillError):
    """Raised when a model descriptor is invalid or requested model is missing."""


class FeatureNotImplementedInPhaseError(TeachSkillError):
    """Raised when accessing interfaces or components planned for future phases.

    Ensures that later-phase functionality is never faked in Phase 1.
    """

    def __init__(self, feature_name: str, target_phase: int) -> None:
        super().__init__(
            f"Feature '{feature_name}' is scheduled for Phase {target_phase} "
            f"and is intentionally not implemented in Phase 1.",
            details={"feature": feature_name, "target_phase": target_phase},
        )
