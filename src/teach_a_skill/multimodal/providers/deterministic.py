"""Deterministic rule-based multimodal provider."""

from typing import Any, Optional

from teach_a_skill.hardware.tiers import HardwareTier
from teach_a_skill.multimodal.context import MultimodalContext
from teach_a_skill.multimodal.grounding import MultimodalGroundingEngine
from teach_a_skill.multimodal.models import MultimodalObservation
from teach_a_skill.multimodal.providers.base import (
    LocalMultimodalProvider,
    ProviderCapabilities,
    ProviderCategory,
)


class DeterministicMultimodalProvider(LocalMultimodalProvider):
    """Deterministic, rule-based provider grounding physical events, UI elements, and speech.
    
    Guarantees 100% deterministic, reproducible, verifiable multimodal observations.
    Runs locally on any hardware tier with minimal memory footprint and zero external network.
    """

    def __init__(
        self,
        grounding_engine: Optional[MultimodalGroundingEngine] = None,
    ) -> None:
        self.grounding_engine = grounding_engine or MultimodalGroundingEngine()
        self._capabilities = ProviderCapabilities(
            provider_id="deterministic",
            category=ProviderCategory.DETERMINISTIC,
            supports_vision=True,
            supports_text=True,
            supports_speech=True,
            supports_deterministic_sampling=True,
            max_context_elements=100,
            supported_hardware_tiers=[
                HardwareTier.BASELINE,
                HardwareTier.STANDARD,
                HardwareTier.HIGH,
            ],
            model_id="deterministic_grounding_rules",
            model_version="1.0.0",
        )

    @property
    def capabilities(self) -> ProviderCapabilities:
        return self._capabilities

    def is_available(self) -> bool:
        return True

    def analyze(self, context: MultimodalContext) -> list[MultimodalObservation]:
        """Compute grounded factual observations from evidence."""
        return self.grounding_engine.ground_context(context)

    def health(self) -> dict[str, Any]:
        return {
            "status": "healthy",
            "provider_id": "deterministic",
            "available": True,
            "category": str(ProviderCategory.DETERMINISTIC),
            "supports_hardware_baseline": True,
        }

    def estimate_cost(self, context: MultimodalContext) -> dict[str, Any]:
        return {
            "estimated_memory_mb": 0.5,
            "estimated_latency_ms": 2.0,
            "requires_gpu": False,
        }
