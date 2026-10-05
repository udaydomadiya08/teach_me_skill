"""Normalized hardware capability profile schema."""

import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass(frozen=True)
class CPUInfo:
    architecture: str
    vendor: str
    model: str
    logical_cores: int
    physical_cores: int
    features: list[str] = field(default_factory=list)
    performance_cores: Optional[int] = None
    efficiency_cores: Optional[int] = None


@dataclass(frozen=True)
class MemoryInfo:
    total_bytes: int
    available_bytes: int

    @property
    def total_gb(self) -> float:
        return round(self.total_bytes / (1024**3), 2)

    @property
    def available_gb(self) -> float:
        return round(self.available_bytes / (1024**3), 2)


@dataclass(frozen=True)
class GPUInfo:
    available: bool
    type: str  # "apple_silicon", "nvidia_cuda", "amd_rocm", "intel_arc", "integrated", "none"
    model: str
    vram_bytes: Optional[int] = None
    unified_memory: bool = False

    @property
    def vram_gb(self) -> Optional[float]:
        if self.vram_bytes is not None:
            return round(self.vram_bytes / (1024**3), 2)
        return None


@dataclass(frozen=True)
class StorageInfo:
    target_path: str
    total_bytes: int
    free_bytes: int

    @property
    def total_gb(self) -> float:
        return round(self.total_bytes / (1024**3), 2)

    @property
    def free_gb(self) -> float:
        return round(self.free_bytes / (1024**3), 2)


@dataclass(frozen=True)
class HardwareProfile:
    """Normalized, platform-independent hardware snapshot."""

    platform: str
    os_version: str
    architecture: str
    cpu: CPUInfo
    memory: MemoryInfo
    gpu: GPUInfo
    accelerators: list[str]
    storage: StorageInfo
    capability_class: str  # "BASELINE", "STANDARD", "HIGH"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metal_available: bool = False
    cuda_available: bool = False
    rocm_available: bool = False
    neural_engine_available: bool = False
    python_runtime: str = field(default_factory=lambda: sys.version.split()[0])
    framework_versions: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize profile to clean JSON-compatible dictionary."""
        return asdict(self)

