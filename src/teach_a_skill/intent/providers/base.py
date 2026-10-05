"""Base provider interface for Phase 7: Intent & Demonstration Understanding."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from teach_a_skill.hardware.tiers import HardwareTier
from teach_a_skill.intent.models import DemonstrationUnderstanding
from teach_a_skill.multimodal.models import MultimodalObservation


class SemanticProviderCategory(str, Enum):
    """Classification of semantic inference providers."""

    DETERMINISTIC = "DETERMINISTIC_PROVIDER"
    MOCK = "MOCK_PROVIDER"
    LOCAL_LLM = "LOCAL_LLM"
    LOCAL_VLM = "LOCAL_VLM"

    def __str__(self) -> str:
        return self.value


@dataclass
class SemanticCapabilities:
    """Declared capabilities and limits of a semantic understanding provider."""

    provider_id: str
    category: SemanticProviderCategory
    supports_task_segmentation: bool = True
    supports_intent_inference: bool = True
    supports_ambiguity_detection: bool = True
    supported_hardware_tiers: list[HardwareTier] = field(
        default_factory=lambda: [HardwareTier.BASELINE, HardwareTier.STANDARD, HardwareTier.HIGH]
    )
    model_id: str = "deterministic_semantic_engine"
    model_version: str = "1.0.0"


class SemanticProvider(ABC):
    """Abstract interface for offline local semantic understanding providers."""

    @property
    @abstractmethod
    def capabilities(self) -> SemanticCapabilities:
        """Return provider capabilities and resource limits."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if local dependencies and model weights are ready."""
        pass

    @abstractmethod
    def infer(
        self,
        session_id: str,
        observations: list[MultimodalObservation],
        context_data: dict[str, Any],
    ) -> DemonstrationUnderstanding:
        """Infer structured demonstration understanding and user intent."""
        pass

    @abstractmethod
    def health(self) -> dict[str, Any]:
        """Return health status, readiness, and memory footprint."""
        pass

    def supports_hardware(self, tier: HardwareTier) -> bool:
        """Check if provider is approved for the given hardware tier."""
        return tier in self.capabilities.supported_hardware_tiers
