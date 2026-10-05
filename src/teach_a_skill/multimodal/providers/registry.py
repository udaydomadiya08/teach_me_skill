"""Provider registry and hardware-aware selection for Phase 6."""

from typing import Any, Optional

from teach_a_skill.core.logging import get_logger
from teach_a_skill.hardware.detector import HardwareDetector
from teach_a_skill.hardware.tiers import HardwareTier
from teach_a_skill.multimodal.providers.base import LocalMultimodalProvider
from teach_a_skill.multimodal.providers.deterministic import DeterministicMultimodalProvider
from teach_a_skill.multimodal.providers.local_vlm import LocalVLMProvider
from teach_a_skill.multimodal.providers.mock import MockMultimodalProvider

logger = get_logger("teach_a_skill.multimodal.providers.registry")


class MultimodalProviderRegistry:
    """Central registry and selector for multimodal intelligence providers."""

    def __init__(self, hardware_tier: Optional[HardwareTier] = None) -> None:
        if hardware_tier is None:
            detector = HardwareDetector()
            profile = detector.get_profile()
            self.hardware_tier = HardwareTier(profile.capability_class)
        else:
            self.hardware_tier = hardware_tier

        self._providers: dict[str, LocalMultimodalProvider] = {}
        self._register_default_providers()

    def _register_default_providers(self) -> None:
        """Register the built-in local providers."""
        # 1. Deterministic Grounding Provider (always available, all hardware tiers)
        self.register_provider("deterministic", DeterministicMultimodalProvider())

        # 2. Mock Provider (for testing and benchmarks)
        self.register_provider("mock", MockMultimodalProvider())

        # 3. Local VLM (checked on local filesystem, graceful MODEL_UNAVAILABLE)
        self.register_provider("local_vlm", LocalVLMProvider())

    def register_provider(self, name: str, provider: LocalMultimodalProvider) -> None:
        """Register a new provider."""
        self._providers[name] = provider

    def get_provider(self, name: str) -> Optional[LocalMultimodalProvider]:
        """Fetch a specific provider by name."""
        return self._providers.get(name)

    def list_providers(self) -> dict[str, dict[str, Any]]:
        """List all registered providers and their readiness status."""
        result = {}
        for name, provider in self._providers.items():
            caps = provider.capabilities
            result[name] = {
                "provider_id": caps.provider_id,
                "category": str(caps.category),
                "model_id": caps.model_id,
                "available": provider.is_available(),
                "supports_hardware": provider.supports_hardware(self.hardware_tier),
                "current_hardware_tier": str(self.hardware_tier),
            }
        return result

    def select_best_provider(
        self,
        preferred_provider: Optional[str] = None,
    ) -> LocalMultimodalProvider:
        """Select an optimal available provider matching hardware tier and policy.
        
        Degradation Order:
        1. If preferred provider is requested, available, and matches hardware tier -> use it.
        2. If STANDARD/HIGH and a real local VLM is available -> use local_vlm.
        3. Fall back safely to deterministic evidence provider (guaranteed available on BASELINE).
        """
        if preferred_provider and preferred_provider in self._providers:
            provider = self._providers[preferred_provider]
            if provider.is_available() and provider.supports_hardware(self.hardware_tier):
                return provider
            elif preferred_provider in ("mock", "deterministic") and provider.is_available():
                return provider
            else:
                logger.warning(
                    f"Requested provider '{preferred_provider}' unavailable or incompatible with tier {self.hardware_tier}. Falling back."
                )

        # Standard / High hardware: try real local VLM if weights are present
        if self.hardware_tier in (HardwareTier.STANDARD, HardwareTier.HIGH):
            vlm = self._providers.get("local_vlm")
            if vlm and vlm.is_available() and vlm.supports_hardware(self.hardware_tier):
                return vlm

        # Safe deterministic fallback guaranteed across all tiers
        det = self._providers.get("deterministic")
        if det and det.is_available():
            return det

        # Ultimate fallback
        return DeterministicMultimodalProvider()
