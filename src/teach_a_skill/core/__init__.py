"""Core foundational services for Teach A Skill."""

from teach_a_skill.core.errors import (
    CapabilityUnavailableError,
    ConfigurationError,
    FeatureNotImplementedInPhaseError,
    HardwareDetectionError,
    ModelRegistryError,
    PrivacyViolationError,
    StorageCorruptionError,
    StorageError,
    StoragePathTraversalError,
    StoragePermissionError,
    TeachSkillError,
)
from teach_a_skill.core.logging import get_logger, setup_logger

__all__ = [
    "TeachSkillError",
    "ConfigurationError",
    "HardwareDetectionError",
    "StorageError",
    "StoragePathTraversalError",
    "StorageCorruptionError",
    "StoragePermissionError",
    "PrivacyViolationError",
    "CapabilityUnavailableError",
    "ModelRegistryError",
    "FeatureNotImplementedInPhaseError",
    "setup_logger",
    "get_logger",
]
