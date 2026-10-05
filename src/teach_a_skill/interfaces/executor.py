"""Skill execution engine interface (Phase 10 contract)."""

from abc import ABC, abstractmethod
from typing import Any


class IExecutor(ABC):
    """Runtime engine for deterministically executing learned skills."""

    @abstractmethod
    def execute(self, skill_id: str, parameters: dict[str, Any]) -> dict[str, Any]:
        """Execute a skill using deterministic actions and adaptive perception."""
        pass

    @abstractmethod
    def abort(self, execution_id: str) -> None:
        """Interrupt and abort an ongoing skill execution."""
        pass
