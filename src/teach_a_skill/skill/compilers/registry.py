"""Skill compiler registry and hardware-aware selection."""

from typing import Any, Optional

from teach_a_skill.hardware.detector import HardwareDetector
from teach_a_skill.hardware.tiers import HardwareTier
from teach_a_skill.skill.compilers.base import SkillCompiler
from teach_a_skill.skill.compilers.deterministic import DeterministicSkillCompiler
from teach_a_skill.skill.compilers.local_llm import LocalLLMCompiler
from teach_a_skill.skill.compilers.mock import MockSkillCompiler


class CompilerRegistry:
    """Central registry and selector for Phase 8 skill compilation engines."""

    def __init__(self, hardware_tier: Optional[HardwareTier] = None) -> None:
        if hardware_tier is None:
            detector = HardwareDetector()
            profile = detector.get_profile()
            self.hardware_tier = HardwareTier(profile.capability_class)
        else:
            self.hardware_tier = hardware_tier

        self._compilers: dict[str, SkillCompiler] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        self.register_compiler("deterministic", DeterministicSkillCompiler())
        self.register_compiler("mock", MockSkillCompiler())
        self.register_compiler("local_llm", LocalLLMCompiler())

    def register_compiler(self, name: str, compiler: SkillCompiler) -> None:
        self._compilers[name] = compiler

    def get_compiler(self, name: str) -> Optional[SkillCompiler]:
        return self._compilers.get(name)

    def list_compilers(self) -> dict[str, dict[str, Any]]:
        result = {}
        for name, compiler in self._compilers.items():
            caps = compiler.capabilities
            result[name] = {
                "compiler_id": caps.compiler_id,
                "category": str(caps.category),
                "compiler_version": caps.compiler_version,
                "available": compiler.is_available(),
                "supports_hardware": self.hardware_tier in caps.supported_hardware_tiers,
                "current_hardware_tier": str(self.hardware_tier),
            }
        return result

    def list_available_compilers(self) -> list[SkillCompiler]:
        return [c for c in self._compilers.values() if c.is_available()]

    def select_best_compiler(
        self,
        preferred_compiler: Optional[str] = None,
    ) -> SkillCompiler:
        """Select an optimal compiler matching hardware tier and policy.
        
        Degradation Order:
        1. Explicit preferred compiler if available.
        2. Local LLM compiler if on STANDARD/HIGH tier and weights are present.
        3. DeterministicSkillCompiler (guaranteed available on all tiers).
        """
        if preferred_compiler and preferred_compiler in self._compilers:
            c = self._compilers[preferred_compiler]
            if c.is_available():
                return c

        if self.hardware_tier in (HardwareTier.STANDARD, HardwareTier.HIGH):
            llm = self._compilers.get("local_llm")
            if llm and llm.is_available():
                return llm

        det = self._compilers.get("deterministic")
        if det and det.is_available():
            return det

        return DeterministicSkillCompiler()
