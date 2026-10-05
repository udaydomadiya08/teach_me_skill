"""Abstract base class and contract for local UI element detectors."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional, Union

from teach_a_skill.perception.models import TextRegion, UIElement


class UIElementDetector(ABC):
    """Abstract interface for local UI element detection."""

    @property
    @abstractmethod
    def detector_id(self) -> str:
        """Unique identifier of the detector."""
        pass

    @property
    @abstractmethod
    def detector_version(self) -> str:
        """Version string of the detection model or heuristic."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if local dependencies and permissions are present."""
        pass

    @abstractmethod
    def detect_elements(
        self,
        image_input: Union[str, Path, bytes],
        frame_id: str = "frame_00000",
        frame_metadata: Optional[dict[str, Any]] = None,
        text_regions: Optional[list[TextRegion]] = None,
    ) -> list[UIElement]:
        """Detect visible or structural UI elements in a frame.

        Args:
            image_input: File path or raw image bytes.
            frame_id: Associated frame ID.
            frame_metadata: Optional frame checkpoint metadata (dimensions, display_id, scale).
            text_regions: Optional pre-extracted OCR text regions to assist detection.

        Returns:
            List of detected UIElement objects.
        """
        pass
