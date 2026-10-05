"""Resource budget calculation and allocation system.

Calculates safe resource boundaries based on hardware tier and available system memory.
"""

from dataclasses import asdict, dataclass
from typing import Any, Optional

from teach_a_skill.hardware.profile import HardwareProfile
from teach_a_skill.hardware.tiers import HardwareTier


@dataclass(frozen=True)
class ResourceBudget:
    """Resource budget defining maximum and preferred operational limits."""

    max_memory_mb: int
    preferred_memory_mb: int
    max_cpu_percent: int
    accelerator_available: bool
    accelerator_type: str
    preferred_model_class: str  # "none", "micro", "small", "medium"
    power_mode: str
    tier: HardwareTier

    def can_allocate_memory(self, required_mb: int) -> bool:
        """Check whether a requested memory allocation falls within max budget."""
        return required_mb <= self.max_memory_mb

    def should_defer_operation(self, required_mb: int) -> bool:
        """Indicate whether heavy work should be deferred due to tight memory constraints."""
        return required_mb > self.preferred_memory_mb

    def to_dict(self) -> dict[str, Any]:
        """Serialize budget to dictionary."""
        data = asdict(self)
        data["tier"] = str(self.tier)
        return data


class BudgetCalculator:
    """Calculates conservative resource budgets based on hardware profile."""

    @staticmethod
    def calculate(
        profile: HardwareProfile,
        power_mode: str = "automatic",
        memory_limit_override_mb: Optional[int] = None,
    ) -> ResourceBudget:
        """Calculate a safe ResourceBudget.

        Rules:
        - Never starve the host operating system.
        - BASELINE: Cap memory to min(2048 MB, 30% of available RAM). CPU max 50%. Model class: "micro" or "none".
        - STANDARD: Cap memory to min(6144 MB, 50% of available RAM). CPU max 70%. Model class: "small".
        - HIGH: Cap memory to min(16384 MB, 65% of available RAM). CPU max 85%. Model class: "medium".
        """
        tier = HardwareTier(profile.capability_class)
        available_mb = int(profile.memory.available_bytes / (1024 * 1024))

        if tier == HardwareTier.BASELINE:
            max_mem = min(2048, max(512, int(available_mb * 0.35)))
            pref_mem = int(max_mem * 0.6)
            max_cpu = 50
            preferred_model_class = "micro"
        elif tier == HardwareTier.STANDARD:
            max_mem = min(6144, max(1536, int(available_mb * 0.50)))
            pref_mem = int(max_mem * 0.7)
            max_cpu = 70
            preferred_model_class = "small"
        else:  # HIGH
            max_mem = min(16384, max(4096, int(available_mb * 0.65)))
            pref_mem = int(max_mem * 0.75)
            max_cpu = 85
            preferred_model_class = "medium"

        if memory_limit_override_mb is not None and memory_limit_override_mb > 0:
            max_mem = min(max_mem, memory_limit_override_mb)
            pref_mem = min(pref_mem, int(max_mem * 0.7))

        return ResourceBudget(
            max_memory_mb=max_mem,
            preferred_memory_mb=pref_mem,
            max_cpu_percent=max_cpu,
            accelerator_available=profile.gpu.available,
            accelerator_type=profile.gpu.type,
            preferred_model_class=preferred_model_class,
            power_mode=power_mode,
            tier=tier,
        )
