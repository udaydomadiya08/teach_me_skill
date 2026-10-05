"""Hardware detection, profiling, tiers, and budgeting subsystem."""

from teach_a_skill.hardware.benchmark import BenchmarkReport, run_benchmark
from teach_a_skill.hardware.budget import BudgetCalculator, ResourceBudget
from teach_a_skill.hardware.detector import HardwareDetector
from teach_a_skill.hardware.capability import (
    CapabilityMatrix,
    CapabilityProfile,
    SupportLevel,
)
from teach_a_skill.hardware.profile import (
    CPUInfo,
    GPUInfo,
    HardwareProfile,
    MemoryInfo,
    StorageInfo,
)
from teach_a_skill.hardware.tiers import HardwareTier, TierClassifier

__all__ = [
    "HardwareDetector",
    "HardwareProfile",
    "CPUInfo",
    "MemoryInfo",
    "GPUInfo",
    "StorageInfo",
    "HardwareTier",
    "TierClassifier",
    "ResourceBudget",
    "BudgetCalculator",
    "BenchmarkReport",
    "run_benchmark",
    "CapabilityProfile",
    "CapabilityMatrix",
    "SupportLevel",
]
