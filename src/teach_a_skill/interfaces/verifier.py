"""Skill verification and recovery interface (Phase 11 contract)."""

from abc import ABC, abstractmethod
from typing import Any


class IVerifier(ABC):
    """Engine for verifying UI state transitions and detecting unexpected deviations."""

    @abstractmethod
    def verify_step(self, expected_state: dict[str, Any], current_state: dict[str, Any]) -> bool:
        """Verify whether an execution step achieved its intended deterministic goal."""
        pass

    @abstractmethod
    def suggest_recovery(self, failure_context: dict[str, Any]) -> dict[str, Any]:
        """Propose deterministic recovery actions when a step fails verification."""
        pass
