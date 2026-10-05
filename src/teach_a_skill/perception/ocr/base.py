"""Abstract base class and contract for local OCR engines."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional, Union

from teach_a_skill.perception.models import OCRResult


class OCRProvider(ABC):
    """Abstract interface for local-only text detection and optical character recognition."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique identifier for this OCR engine implementation."""
        pass

    @property
    @abstractmethod
    def provider_version(self) -> str:
        """Version string of the OCR engine / model."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if local dependencies, models, and binaries are present and functional."""
        pass

    @abstractmethod
    def detect_text(
        self,
        image_input: Union[str, Path, bytes],
        frame_id: str = "frame_00000",
        options: Optional[dict[str, Any]] = None,
    ) -> OCRResult:
        """Perform text detection and recognition on a single image frame.

        Args:
            image_input: File path or raw image bytes.
            frame_id: Associated frame ID.
            options: Optional provider-specific configuration.

        Returns:
            OCRResult containing structured TextRegions with confidence and coordinates.
        """
        pass
