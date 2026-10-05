"""Mock UI element detector for deterministic testing and reproducible benchmarks."""

from pathlib import Path
from typing import Any, Optional, Union

from teach_a_skill.perception.coordinates import CoordinateTransformer
from teach_a_skill.perception.detection.base import UIElementDetector
from teach_a_skill.perception.models import (
    BoundingBox,
    PerceptionSource,
    TextRegion,
    UIElement,
    UIElementType,
)


class MockUIDetector(UIElementDetector):
    """Deterministic synthetic UI element detector."""

    def __init__(
        self,
        canned_elements: Optional[list[tuple[UIElementType, tuple[float, float, float, float], float]]] = None,
        available: bool = True,
    ) -> None:
        self._canned_elements = canned_elements
        self._available = available

    @property
    def detector_id(self) -> str:
        return "mock_detector"

    @property
    def detector_version(self) -> str:
        return "mock-v1"

    def is_available(self) -> bool:
        return self._available

    def detect_elements(
        self,
        image_input: Union[str, Path, bytes],
        frame_id: str = "frame_00000",
        frame_metadata: Optional[dict[str, Any]] = None,
        text_regions: Optional[list[TextRegion]] = None,
    ) -> list[UIElement]:
        if not self._available:
            raise RuntimeError("MockUIDetector configured as unavailable.")

        w = int(frame_metadata.get("width", 1920)) if frame_metadata else 1920
        h = int(frame_metadata.get("height", 1080)) if frame_metadata else 1080
        transformer = CoordinateTransformer(frame_width=w, frame_height=h)

        entries = self._canned_elements
        if entries is None:
            entries = [
                (UIElementType.BUTTON_LIKE, (500.0, 100.0, 80.0, 30.0), 0.95),
                (UIElementType.BUTTON_LIKE, (600.0, 100.0, 80.0, 30.0), 0.95),
                (UIElementType.INPUT_LIKE, (200.0, 100.0, 250.0, 30.0), 0.90),
                (UIElementType.PANEL, (50.0, 50.0, 700.0, 400.0), 0.85),
            ]

        elements: list[UIElement] = []
        for idx, (el_type, (px, py, pw, ph), conf) in enumerate(entries):
            bbox = transformer.create_bounding_box(px, py, pw, ph)
            e_id = f"elem_m_{idx + 1:04d}_{frame_id}"
            elements.append(
                UIElement(
                    element_id=e_id,
                    frame_id=frame_id,
                    element_type=el_type,
                    bbox=bbox,
                    confidence=conf,
                    sources=[PerceptionSource.IMAGE.value],
                    reading_order=idx + 1,
                    provenance={"mock": True, "frame_id": frame_id},
                )
            )

        return elements
