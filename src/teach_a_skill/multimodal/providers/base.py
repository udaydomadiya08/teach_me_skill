"""Provider interface for Phase 6: Local Multimodal Intelligence."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from teach_a_skill.hardware.tiers import HardwareTier
from teach_a_skill.multimodal.context import MultimodalContext
from teach_a_skill.multimodal.models import MultimodalObservation


class ProviderCategory(str, Enum):
    """Classification of multimodal inference providers."""

    DETERMINISTIC = "DETERMINISTIC_PROVIDER"
    MOCK = "MOCK_PROVIDER"
    LOCAL_VLM = "LOCAL_VLM"
    LOCAL_LLM_WITH_VISION = "LOCAL_LLM_WITH_VISION"
    LOCAL_EMBEDDING_MODEL = "LOCAL_EMBEDDING_MODEL"

    def __str__(self) -> str:
        return self.value


@dataclass
class ProviderCapabilities:
    """Declared capabilities and boundaries of a multimodal provider."""

    provider_id: str
    category: ProviderCategory
    supports_vision: bool = True
    supports_text: bool = True
    supports_speech: bool = False
    supports_deterministic_sampling: bool = True
    max_context_elements: int = 50
    supported_hardware_tiers: list[HardwareTier] = field(
        default_factory=lambda: [HardwareTier.BASELINE, HardwareTier.STANDARD, HardwareTier.HIGH]
    )
    model_id: str = "deterministic_rules"
    model_version: str = "1.0.0"


class LocalMultimodalProvider(ABC):
    """Abstract interface for local multimodal providers.
    
    CRITICAL:
    All providers must run locally without network access.
    No automatic model downloads are permitted.
    Outputs must be structured multimodal observations describing what was observed,
    not user goals, intents, or action recommendations.
    """

    @property
    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        """Return provider capabilities and resource limits."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if local dependencies/model weights are present and ready."""
        pass

    @abstractmethod
    def analyze(self, context: MultimodalContext) -> list[MultimodalObservation]:
        """Analyze a multimodal context and return structured factual observations."""
        pass

    @abstractmethod
    def health(self) -> dict[str, Any]:
        """Return provider health status, memory footprint, and readiness."""
        pass

    def estimate_cost(self, context: MultimodalContext) -> dict[str, Any]:
        """Estimate computational cost (memory, latency, operations) for a context."""
        return {
            "estimated_memory_mb": 0.0,
            "estimated_latency_ms": 1.0,
            "requires_gpu": False,
        }

    def supports_hardware(self, tier: HardwareTier) -> bool:
        """Check if provider is approved for the given hardware tier."""
        return tier in self.capabilities.supported_hardware_tiers
