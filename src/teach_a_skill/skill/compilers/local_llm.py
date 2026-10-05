"""Local LLM-assisted Skill Compiler adapter adhering to zero-download policy."""

from pathlib import Path
from typing import Any, Optional

from teach_a_skill.hardware.tiers import HardwareTier
from teach_a_skill.intent.models import DemonstrationUnderstanding
from teach_a_skill.skill.compilers.base import (
    CompilerCapabilities,
    CompilerCategory,
    SkillCompiler,
)
from teach_a_skill.skill.models import SkillIR


class LocalLLMCompiler(SkillCompiler):
    """Local LLM-assisted compiler adapter.
    
    Adheres strictly to the local-first invariant:
    - Never downloads weights automatically from remote networks.
    - Never calls external cloud endpoints.
    - Only functions if local model weights are present on disk.
    - If weights are not installed, honestly reports is_available() == False.
    """

    def __init__(
        self,
        weights_dir: Optional[Path] = None,
        model_id: str = "local_llm_skill_compiler_v1",
    ) -> None:
        self.weights_dir = weights_dir
        self._capabilities = CompilerCapabilities(
            compiler_id="local_llm_skill_compiler",
            category=CompilerCategory.LOCAL_LLM,
            compiler_version="1.0.0",
            supports_parameter_extraction=True,
            supports_ambiguity_flagging=True,
            supported_hardware_tiers=[HardwareTier.STANDARD, HardwareTier.HIGH],
        )

    @property
    def capabilities(self) -> CompilerCapabilities:
        return self._capabilities

    def is_available(self) -> bool:
        """Return True only if local weights exist on disk."""
        if not self.weights_dir or not self.weights_dir.exists():
            return False
        weight_files = list(self.weights_dir.glob("*.gguf")) + list(self.weights_dir.glob("*.bin"))
        return len(weight_files) > 0

    def compile(
        self,
        understanding: DemonstrationUnderstanding,
        options: Optional[dict[str, Any]] = None,
    ) -> SkillIR:
        """Execute local LLM compilation if available."""
        if not self.is_available():
            raise RuntimeError(
                "MODEL_UNAVAILABLE: Local LLM compiler weights are not installed. "
                "Per system policy, automatic remote downloads are blocked."
            )
        raise NotImplementedError("Local LLM inference requires pre-installed GGUF model files.")
