"""OCR (Optical Character Recognition) interface (Phase 5 contract)."""

from abc import ABC, abstractmethod
from typing import Any


class IOCREngine(ABC):
    """Local text extraction interface for raster frames."""

    @abstractmethod
    def extract_text(self, image_data: bytes) -> list[dict[str, Any]]:
        """Extract text boxes, recognized strings, and confidence scores."""
        pass
