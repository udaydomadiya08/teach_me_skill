"""Deterministic visual geometry UI element detector (Screen-Only Fallback)."""

import io
from pathlib import Path
from typing import Any, Optional, Union

import numpy as np
from PIL import Image

from teach_a_skill.core.logging import get_logger
from teach_a_skill.perception.coordinates import CoordinateTransformer
from teach_a_skill.perception.models import (
    BoundingBox,
    PerceptionSource,
    TextRegion,
    UIElement,
    UIElementType,
)
from teach_a_skill.perception.detection.base import UIElementDetector

logger = get_logger("teach_a_skill.perception.detection.geometry")


class GeometryDetector(UIElementDetector):
    """Local, deterministic visual geometry detector identifying rectangular and contour UI elements."""

    def __init__(
        self,
        min_element_area: int = 144,  # e.g. 12x12
        max_element_area: Optional[int] = None,
        canny_thresh1: int = 50,
        canny_thresh2: int = 150,
    ) -> None:
        self.min_element_area = min_element_area
        self.max_element_area = max_element_area
        self.canny_thresh1 = canny_thresh1
        self.canny_thresh2 = canny_thresh2

    @property
    def detector_id(self) -> str:
        return "geometry_detector"

    @property
    def detector_version(self) -> str:
        return "geometry-v1"

    def is_available(self) -> bool:
        try:
            import cv2  # noqa: F401
            return True
        except ImportError:
            return False

    def detect_elements(
        self,
        image_input: Union[str, Path, bytes],
        frame_id: str = "frame_00000",
        frame_metadata: Optional[dict[str, Any]] = None,
        text_regions: Optional[list[TextRegion]] = None,
    ) -> list[UIElement]:
        import cv2

        # 1. Load image into numpy array
        if isinstance(image_input, (str, Path)):
            pil_img = Image.open(image_input)
        elif isinstance(image_input, bytes):
            pil_img = Image.open(io.BytesIO(image_input))
        else:
            raise ValueError(f"Unsupported image input type: {type(image_input)}")

        w, h = pil_img.size
        cv_img = cv2.cvtColor(np.array(pil_img.convert("RGB")), cv2.COLOR_RGB2BGR)

        scale_factor = 1.0
        display_id = None
        if frame_metadata:
            scale_factor = float(frame_metadata.get("scale_factor", 1.0))
            display_id = frame_metadata.get("display_id")

        transformer = CoordinateTransformer(
            frame_width=w,
            frame_height=h,
            scale_factor=scale_factor,
            display_id=display_id,
        )

        # 2. Convert to grayscale and detect edges
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, self.canny_thresh1, self.canny_thresh2)

        # Morphological dilation to connect component edges
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        dilated = cv2.dilate(edges, kernel, iterations=1)

        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        max_allowed_area = self.max_element_area or int(w * h * 0.95)
        raw_boxes: list[tuple[float, float, float, float]] = []

        for cnt in contours:
            px, py, pw, ph = cv2.boundingRect(cnt)
            area = pw * ph
            if self.min_element_area <= area <= max_allowed_area:
                raw_boxes.append((float(px), float(py), float(pw), float(ph)))

        # Also incorporate OCR text regions if provided to ensure text elements are present
        if text_regions:
            for tr in text_regions:
                raw_boxes.append((tr.bbox.x, tr.bbox.y, tr.bbox.width, tr.bbox.height))

        # Sort raw boxes deterministically: top-to-bottom, left-to-right
        raw_boxes.sort(key=lambda b: (round(b[1] / 15.0) * 15.0, b[0], b[2], b[3]))

        # Remove redundant near-duplicate boxes (IoU > 0.85)
        filtered_boxes: list[BoundingBox] = []
        for bx, by, bw, bh in raw_boxes:
            curr_box = transformer.create_bounding_box(bx, by, bw, bh)
            is_duplicate = False
            for fb in filtered_boxes:
                if curr_box.intersection_over_union(fb) > 0.85:
                    is_duplicate = True
                    break
            if not is_duplicate:
                filtered_boxes.append(curr_box)

        # 3. Classify into neutral structural UI categories
        elements: list[UIElement] = []
        for idx, bbox in enumerate(filtered_boxes):
            el_type = self._classify_geometry(bbox.width, bbox.height, w, h)
            e_id = f"elem_geom_{idx + 1:05d}_{frame_id}"

            elements.append(
                UIElement(
                    element_id=e_id,
                    frame_id=frame_id,
                    element_type=el_type,
                    bbox=bbox,
                    confidence=0.85,
                    sources=[PerceptionSource.IMAGE.value],
                    reading_order=idx + 1,
                    provenance={
                        "detector": self.detector_id,
                        "algorithm": "opencv_canny_contour",
                        "frame_id": frame_id,
                    },
                )
            )

        return elements

    def _classify_geometry(self, width: float, height: float, frame_w: int, frame_h: int) -> UIElementType:
        """Classify geometric box into neutral structural taxonomy."""
        aspect = width / max(1.0, height)
        area_ratio = (width * height) / float(frame_w * frame_h)

        # Very large containers
        if area_ratio > 0.25:
            return UIElementType.PANEL

        # Checkbox / Radio like: small squares
        if 10.0 <= width <= 32.0 and 10.0 <= height <= 32.0 and 0.8 <= aspect <= 1.25:
            return UIElementType.CHECKBOX_LIKE

        # Icons: slightly larger square-ish items
        if 16.0 <= width <= 64.0 and 16.0 <= height <= 64.0 and 0.75 <= aspect <= 1.35:
            return UIElementType.ICON_LIKE

        # Buttons: typical horizontal aspect ratio and bounded height
        if 1.5 <= aspect <= 6.0 and 18.0 <= height <= 65.0 and width <= 350.0:
            return UIElementType.BUTTON_LIKE

        # Input fields: elongated horizontal box
        if 3.5 <= aspect <= 16.0 and 18.0 <= height <= 55.0:
            return UIElementType.INPUT_LIKE

        # Dropdowns / Combos
        if 4.0 <= aspect <= 14.0 and 20.0 <= height <= 50.0:
            return UIElementType.DROPDOWN_LIKE

        # Medium panels / window regions
        if width > 200.0 and height > 150.0:
            return UIElementType.WINDOW_REGION

        return UIElementType.UNKNOWN_REGION
