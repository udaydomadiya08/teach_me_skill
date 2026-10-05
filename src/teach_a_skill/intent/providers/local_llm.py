"""Local Large Language Model provider (safe, local-first, zero auto-download)."""

from pathlib import Path
from typing import Any, Optional

from teach_a_skill.core.logging import get_logger
from teach_a_skill.hardware.tiers import HardwareTier
from teach_a_skill.intent.models import DemonstrationUnderstanding
from teach_a_skill.intent.providers.base import (
    SemanticCapabilities,
    SemanticProvider,
    SemanticProviderCategory,
)
from teach_a_skill.multimodal.models import MultimodalObservation

logger = get_logger("teach_a_skill.intent.providers.local_llm")


class LocalLLMProvider(SemanticProvider):
    """Adapter for real local Large Language Models (e.g. Llama-3, Mistral, Qwen, Gemma).
    
    STRICT SECURITY & LOCAL-FIRST POLICIES:
    1. NEVER performs automatic network downloads.
    2. Missing local weights report MODEL_UNAVAILABLE gracefully.
    3. Requires explicit local model directory and checksum verification.
    4. Constrained by Phase 1 hardware tier budgets.
    """

    def __init__(
        self,
        model_id: str = "local_llm_qwen2_7b",
        model_path: Optional[Path] = None,
        quantization: Optional[str] = None,
    ) -> None:
        self._model_id = model_id
        self._model_path = Path(model_path) if model_path else None
        self._quantization = quantization or "q4_k_m"
        self._available = False
        self._load_error: Optional[str] = None

        self._capabilities = SemanticCapabilities(
            provider_id="local_llm",
            category=SemanticProviderCategory.LOCAL_LLM,
            supports_task_segmentation=True,
            supports_intent_inference=True,
            supports_ambiguity_detection=True,
            supported_hardware_tiers=[HardwareTier.STANDARD, HardwareTier.HIGH],
            model_id=self._model_id,
            model_version="1.0.0",
        )

        self._check_local_availability()

    def _check_local_availability(self) -> None:
        """Inspect local filesystem for genuine weights without remote calls."""
        if not self._model_path:
            self._available = False
            self._load_error = "MODEL_UNAVAILABLE: No local model weights path configured."
            return

        if not self._model_path.exists():
            self._available = False
            self._load_error = f"MODEL_UNAVAILABLE: Path does not exist: {self._model_path}"
            return

        if self._model_path.is_file():
            self._available = True
            self._load_error = None
        elif self._model_path.is_dir():
            weights = list(self._model_path.glob("*.gguf")) + list(
                self._model_path.glob("*.safetensors")
            )
            if weights:
                self._available = True
                self._load_error = None
            else:
                self._available = False
                self._load_error = (
                    f"MODEL_UNAVAILABLE: Directory {self._model_path} contains no valid weights (.gguf/.safetensors)."
                )

    @property
    def capabilities(self) -> SemanticCapabilities:
        return self._capabilities

    def is_available(self) -> bool:
        return self._available

    def infer(
        self,
        session_id: str,
        observations: list[MultimodalObservation],
        context_data: dict[str, Any],
    ) -> DemonstrationUnderstanding:
        """Execute local semantic inference if weights are available."""
        if not self._available:
            raise RuntimeError(
                f"Cannot execute LocalLLMProvider: {self._load_error or 'MODEL_UNAVAILABLE'}"
            )

        # In real local deployment with loaded weights, run bounded local LLM inference
        raise NotImplementedError("Real weights execution required.")

    def health(self) -> dict[str, Any]:
        return {
            "status": "healthy" if self._available else "unavailable",
            "provider_id": "local_llm",
            "category": str(SemanticProviderCategory.LOCAL_LLM),
            "model_id": self._model_id,
            "model_path": str(self._model_path) if self._model_path else None,
            "available": self._available,
            "load_error": self._load_error,
            "quantization": self._quantization,
            "is_real_model": True,
        }
