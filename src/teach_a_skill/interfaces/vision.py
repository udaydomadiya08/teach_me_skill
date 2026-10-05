"""Vision and UI element perception interface (Phase 5/6 contract)."""

from abc import ABC, abstractmethod
from typing import Any


class IVisionEngine(ABC):
    """Local visual perception interface for UI element detection and layout grounding."""

    @abstractmethod
    def detect_elements(self, image_data: bytes) -> list[dict[str, Any]]:
        """Detect interactive UI components, bounding boxes, and visual labels."""
        pass
