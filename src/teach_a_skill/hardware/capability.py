"""Hardware capability profiling and task compatibility matrix."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional

from teach_a_skill.hardware.profile import HardwareProfile
from teach_a_skill.hardware.tiers import HardwareTier


class SupportLevel(str, Enum):
    """Level of capability support."""

    SUPPORTED = "supported"
    OPTIONAL = "optional"
    UNSUPPORTED = "unsupported"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class CapabilityProfile:
    """Hardware capability profile mapping hardware metrics to intelligence readiness."""

    tier: HardwareTier
    supported_tasks: dict[str, SupportLevel] = field(default_factory=dict)
    supported_model_classes: list[str] = field(default_factory=list)
    max_context_length: int = 2048
    recommended_concurrency: int = 1
    notes: str = ""

    def is_task_supported(self, task_name: str) -> bool:
        """Check if a task is supported or optional under this profile."""
        lvl = self.supported_tasks.get(task_name.lower())
        return lvl in (SupportLevel.SUPPORTED, SupportLevel.OPTIONAL)

    def get_support_level(self, task_name: str) -> SupportLevel:
        """Get exact support level for task."""
        return self.supported_tasks.get(task_name.lower(), SupportLevel.UNSUPPORTED)

    def to_dict(self) -> dict[str, Any]:
        """Convert capability profile to dictionary."""
        data = asdict(self)
        data["tier"] = self.tier.value
        data["supported_tasks"] = {k: str(v) for k, v in self.supported_tasks.items()}
        return data


class CapabilityMatrix:
    """Evaluates hardware profiles to produce explainable CapabilityProfiles."""

    @classmethod
    def evaluate(cls, profile: HardwareProfile) -> CapabilityProfile:
        """Derive capability profile deterministically from hardware profile."""
        tier_str = profile.capability_class.upper()
        if tier_str == "HIGH":
            tier = HardwareTier.HIGH
            tasks = {
                "ocr": SupportLevel.SUPPORTED,
                "stt": SupportLevel.SUPPORTED,
                "text_semantics": SupportLevel.SUPPORTED,
                "text_classification": SupportLevel.SUPPORTED,
                "small_vlm": SupportLevel.SUPPORTED,
                "medium_vlm": SupportLevel.SUPPORTED,
                "large_vlm": SupportLevel.OPTIONAL,
                "embedding": SupportLevel.SUPPORTED,
                "reranking": SupportLevel.SUPPORTED,
                "skill_validation": SupportLevel.SUPPORTED,
                "deterministic_reasoning": SupportLevel.SUPPORTED,
                "multimodal_grounding": SupportLevel.SUPPORTED,
                "verification_assistance": SupportLevel.SUPPORTED,
                "recovery_assistance": SupportLevel.SUPPORTED,
            }
            model_classes = ["deterministic", "micro", "small", "medium", "large"]
            max_ctx = 8192
            concurrency = 4
            notes = "High-tier workstation/GPU setup capable of medium and large models."

        elif tier_str == "STANDARD":
            tier = HardwareTier.STANDARD
            tasks = {
                "ocr": SupportLevel.SUPPORTED,
                "stt": SupportLevel.SUPPORTED,
                "text_semantics": SupportLevel.SUPPORTED,
                "text_classification": SupportLevel.SUPPORTED,
                "small_vlm": SupportLevel.SUPPORTED,
                "medium_vlm": SupportLevel.OPTIONAL,
                "large_vlm": SupportLevel.UNSUPPORTED,
                "embedding": SupportLevel.SUPPORTED,
                "reranking": SupportLevel.SUPPORTED,
                "skill_validation": SupportLevel.SUPPORTED,
                "deterministic_reasoning": SupportLevel.SUPPORTED,
                "multimodal_grounding": SupportLevel.SUPPORTED,
                "verification_assistance": SupportLevel.SUPPORTED,
                "recovery_assistance": SupportLevel.SUPPORTED,
            }
            model_classes = ["deterministic", "micro", "small"]
            max_ctx = 4096
            concurrency = 2
            notes = "Standard laptop/desktop with moderate RAM/acceleration."

        else:
            tier = HardwareTier.BASELINE
            tasks = {
                "ocr": SupportLevel.SUPPORTED,
                "stt": SupportLevel.SUPPORTED,
                "text_semantics": SupportLevel.SUPPORTED,
                "text_classification": SupportLevel.SUPPORTED,
                "small_vlm": SupportLevel.OPTIONAL,
                "medium_vlm": SupportLevel.UNSUPPORTED,
                "large_vlm": SupportLevel.UNSUPPORTED,
                "embedding": SupportLevel.SUPPORTED,
                "reranking": SupportLevel.SUPPORTED,
                "skill_validation": SupportLevel.SUPPORTED,
                "deterministic_reasoning": SupportLevel.SUPPORTED,
                "multimodal_grounding": SupportLevel.SUPPORTED,
                "verification_assistance": SupportLevel.SUPPORTED,
                "recovery_assistance": SupportLevel.SUPPORTED,
            }
            model_classes = ["deterministic", "micro"]
            max_ctx = 2048
            concurrency = 1
            notes = "Baseline system. Prioritizes deterministic methods and quantized micro-models."

        return CapabilityProfile(
            tier=tier,
            supported_tasks=tasks,
            supported_model_classes=model_classes,
            max_context_length=max_ctx,
            recommended_concurrency=concurrency,
            notes=notes,
        )
