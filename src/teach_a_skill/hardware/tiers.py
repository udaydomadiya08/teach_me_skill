"""Hardware performance tier classification.

Provides deterministic, conservative classification of host hardware capabilities.
"""

from enum import Enum
from typing import Optional

from teach_a_skill.hardware.profile import CPUInfo, GPUInfo, MemoryInfo


class HardwareTier(str, Enum):
    """Normalized hardware capability tiers."""

    BASELINE = "BASELINE"
    STANDARD = "STANDARD"
    HIGH = "HIGH"

    def __str__(self) -> str:
        return self.value


class TierClassifier:
    """Deterministic, conservative classifier for hardware profiles."""

    @staticmethod
    def classify(
        cpu: CPUInfo,
        memory: MemoryInfo,
        gpu: GPUInfo,
        accelerators: list[str],
        power_mode: Optional[str] = None,
    ) -> HardwareTier:
        """Classify hardware into BASELINE, STANDARD, or HIGH.

        Conservative rules:
        - If free memory is critically constrained (< 2.5 GB), downgrade.
        - High requires: >= 24 GB RAM, >= 8 logical cores, and hardware acceleration
          (Apple Silicon Pro/Max/Ultra or dedicated GPU with >= 8 GB VRAM or unified memory >= 24 GB).
        - Standard requires: >= 12 GB RAM, >= 6 logical cores, and acceptable acceleration or strong CPU.
        - Baseline: all modest laptops, CPU-only machines, or machines with <= 8 GB RAM.
        """
        ram_gb = memory.total_gb
        avail_gb = memory.available_gb
        cores = cpu.logical_cores
        has_accel = gpu.available and (
            gpu.type in ("apple_silicon", "nvidia_cuda", "amd_rocm", "intel_arc")
            or len(accelerators) > 0
        )

        tier = HardwareTier.BASELINE

        # High tier requirements:
        # 1. Total RAM >= 24 GB
        # 2. Cores >= 8
        # 3. High-grade accelerator (Apple Silicon unified >= 24GB or dedicated VRAM >= 8GB)
        # 4. Available RAM >= 6 GB
        if ram_gb >= 24.0 and cores >= 8 and avail_gb >= 6.0:
            if gpu.type == "apple_silicon" and ram_gb >= 24.0:
                tier = HardwareTier.HIGH
            elif gpu.type == "nvidia_cuda" and (gpu.vram_gb or 0) >= 8.0:
                tier = HardwareTier.HIGH
            elif gpu.type == "amd_rocm" and (gpu.vram_gb or 0) >= 8.0:
                tier = HardwareTier.HIGH

        # Standard tier requirements:
        # 1. Total RAM >= 12 GB
        # 2. Cores >= 6
        # 3. Available RAM >= 3 GB
        # 4. Acceleration available OR modern high-core CPU
        if tier == HardwareTier.BASELINE and ram_gb >= 12.0 and cores >= 6 and avail_gb >= 3.0:
            if has_accel:
                tier = HardwareTier.STANDARD
            elif cores >= 8 and ram_gb >= 16.0:
                # Strong CPU-only machine
                tier = HardwareTier.STANDARD

        # Conservative safety check: if currently available memory is critically low (< 2.5 GB),
        # force downgrade to BASELINE regardless of raw specs to prevent OS starvation/OOM.
        if avail_gb < 2.5 and tier != HardwareTier.BASELINE:
            tier = HardwareTier.BASELINE

        # Thermal/battery throttling constraint: if in low power mode, degrade one tier
        if power_mode in ("low_power", "battery_saver") and tier == HardwareTier.HIGH:
            tier = HardwareTier.STANDARD

        return tier
