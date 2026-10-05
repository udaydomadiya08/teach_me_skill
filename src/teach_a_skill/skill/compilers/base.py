"""Base interface and capability definitions for Skill Compilers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from teach_a_skill.hardware.tiers import HardwareTier
from teach_a_skill.intent.models import DemonstrationUnderstanding
from teach_a_skill.skill.models import SkillIR


class CompilerCategory(str, Enum):
    """Categorization of compilation engines."""

    DETERMINISTIC = "DETERMINISTIC"
    MOCK = "MOCK"
    LOCAL_LLM = "LOCAL_LLM"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class CompilerCapabilities:
    """Declared capabilities and constraints of a skill compiler."""

    compiler_id: str
    category: CompilerCategory
    compiler_version: str = "1.0.0"
    supports_parameter_extraction: bool = True
    supports_ambiguity_flagging: bool = True
    supported_hardware_tiers: list[HardwareTier] = field(
        default_factory=lambda: [
            HardwareTier.BASELINE,
            HardwareTier.STANDARD,
            HardwareTier.HIGH,
        ]
    )


class SkillCompiler(ABC):
    """Abstract interface for compiling semantic demonstration understanding into Skill IR."""

    @property
    @abstractmethod
    def capabilities(self) -> CompilerCapabilities:
        """Return compiler capability descriptors."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if compiler dependencies and local models are present."""
        pass

    @abstractmethod
    def compile(
        self,
        understanding: DemonstrationUnderstanding,
        options: Optional[dict[str, Any]] = None,
    ) -> SkillIR:
        """Compile Phase 7 demonstration understanding into portable Skill IR.
        
        Must NOT execute or replay the skill.
        """
        pass
