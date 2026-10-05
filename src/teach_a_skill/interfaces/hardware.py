"""Hardware detection and profiling interfaces."""

from abc import ABC, abstractmethod
from typing import Any


class IHardwareDetector(ABC):
    """Interface for querying system hardware characteristics without side effects."""

    @abstractmethod
    def detect_cpu(self) -> dict[str, Any]:
        """Detect CPU architecture, vendor, model, logical/physical cores."""
        pass

    @abstractmethod
    def detect_memory(self) -> dict[str, Any]:
        """Detect total and currently available system RAM in bytes."""
        pass

    @abstractmethod
    def detect_gpu(self) -> dict[str, Any]:
        """Detect available GPU, accelerator devices (Apple Metal, CUDA, etc.)."""
        pass

    @abstractmethod
    def detect_storage(self, target_path: str) -> dict[str, Any]:
        """Detect total and free storage space on target volume in bytes."""
        pass

    @abstractmethod
    def get_profile(self) -> Any:
        """Return the normalized hardware capability profile."""
        pass
