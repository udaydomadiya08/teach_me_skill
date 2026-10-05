"""Skill definition and persistence contracts."""

from abc import ABC, abstractmethod
from typing import Any, Optional


class ISkill(ABC):
    """Abstract skill representation representing a reusable learned computer task."""

    @property
    @abstractmethod
    def skill_id(self) -> str:
        """Unique identifier of the skill."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of the skill."""
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        """Semantic version of the skill schema."""
        pass

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Serialize skill specification to dictionary."""
        pass


class ISkillStore(ABC):
    """Persistence interface for saving, listing, and loading learned skills."""

    @abstractmethod
    def save_skill(self, skill: ISkill) -> None:
        """Persist a skill definition to local storage."""
        pass

    @abstractmethod
    def get_skill(self, skill_id: str) -> Optional[ISkill]:
        """Load a skill definition by ID."""
        pass

    @abstractmethod
    def list_skills(self) -> list[ISkill]:
        """Enumerate all available local skills."""
        pass

    @abstractmethod
    def delete_skill(self, skill_id: str) -> bool:
        """Delete a skill by ID."""
        pass
