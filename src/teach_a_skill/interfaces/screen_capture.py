"""Screen capture interface (Phase 2 contract)."""

from abc import ABC, abstractmethod
from typing import Any, Optional


class IScreenCapture(ABC):
    """Deterministic OS-level screen capture interface."""

    @abstractmethod
    def capture_frame(self, display_id: Optional[int] = None) -> Any:
        """Capture a single frame from the specified display."""
        pass

    @abstractmethod
    def get_display_info(self) -> list[dict[str, Any]]:
        """Query connected display geometries, scaling factors, and refresh rates."""
        pass
