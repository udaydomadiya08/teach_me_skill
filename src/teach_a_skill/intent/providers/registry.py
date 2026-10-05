"""Semantic provider registry and hardware-aware selection."""

from typing import Any, Optional

from teach_a_skill.core.logging import get_logger
from teach_a_skill.hardware.detector import HardwareDetector
from teach_a_skill.hardware.tiers import HardwareTier
from teach_a_skill.intent.providers.base import SemanticProvider
from teach_a_skill.intent.providers.deterministic import DeterministicSemanticProvider
from teach_a_skill.intent.providers.local_llm import LocalLLMProvider
from teach_a_skill.intent.providers.mock import MockSemanticProvider

logger = get_logger("teach_a_skill.intent.providers.registry")


class SemanticProviderRegistry:
    """Central registry and selector for Phase 7 semantic understanding providers."""

    def __init__(self, hardware_tier: Optional[HardwareTier] = None) -> None:
        if hardware_tier is None:
            detector = HardwareDetector()
            profile = detector.get_profile()
            self.hardware_tier = HardwareTier(profile.capability_class)
        else:
            self.hardware_tier = hardware_tier

        self._providers: dict[str, SemanticProvider] = {}
        self._register_default_providers()

    def _register_default_providers(self) -> None:
        """Register the default local providers."""
        self.register_provider("deterministic", DeterministicSemanticProvider())
        self.register_provider("mock", MockSemanticProvider())
        self.register_provider("local_llm", LocalLLMProvider())

    def register_provider(self, name: str, provider: SemanticProvider) -> None:
        """Register a provider instance."""
        self._providers[name] = provider

    def get_provider(self, name: str) -> Optional[SemanticProvider]:
        """Fetch a specific provider by name."""
        return self._providers.get(name)

    def list_providers(self) -> dict[str, dict[str, Any]]:
        """List all registered providers and their status."""
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

    def list_available_providers(self) -> list[SemanticProvider]:
        """List provider instances that are currently available."""
        return [p for p in self._providers.values() if p.is_available()]

    def select_best_provider(
        self,
        preferred_provider: Optional[str] = None,
    ) -> SemanticProvider:
        """Select an optimal available provider matching hardware tier and policy.
        
        Degradation Order:
        1. Explicit preferred provider if available.
        2. Real local LLM if on STANDARD/HIGH tier and weights are present.
        3. Fall back safely to DeterministicSemanticProvider (always available on BASELINE).
        """
        if preferred_provider and preferred_provider in self._providers:
            provider = self._providers[preferred_provider]
            if provider.is_available() and provider.supports_hardware(self.hardware_tier):
                return provider
            elif preferred_provider in ("mock", "deterministic") and provider.is_available():
                return provider

        # Standard / High hardware: try real local LLM if weights are installed
        if self.hardware_tier in (HardwareTier.STANDARD, HardwareTier.HIGH):
            llm = self._providers.get("local_llm")
            if llm and llm.is_available() and llm.supports_hardware(self.hardware_tier):
                return llm

        # Safe deterministic fallback guaranteed across all tiers
        det = self._providers.get("deterministic")
        if det and det.is_available():
            return det

        return DeterministicSemanticProvider()
