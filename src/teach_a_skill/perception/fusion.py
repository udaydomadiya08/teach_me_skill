"""Deterministic multi-source fusion merging visual regions, accessibility elements, and OCR text."""

from typing import Optional

from teach_a_skill.perception.models import (
    PerceptionSource,
    TextRegion,
    UIElement,
    UIElementType,
)
from teach_a_skill.perception.reading_order import DeterministicReadingOrder


class PerceptionFusion:
    """Combines detected UI regions, accessibility trees, and OCR text into a unified perception layer."""

    def __init__(self, iou_match_threshold: float = 0.5) -> None:
        self.iou_match_threshold = iou_match_threshold

    def fuse(
        self,
        geometric_elements: list[UIElement],
        accessibility_elements: list[UIElement],
        text_regions: list[TextRegion],
        frame_id: str,
    ) -> list[UIElement]:
        """Merge multiple perception sources into a deduplicated, enriched UI element list."""
        merged_elements: list[UIElement] = []

        # 1. Start with accessibility elements if present (high structural fidelity)
        # and geometric elements.
        candidate_elements: list[UIElement] = list(accessibility_elements)

        # Merge in geometric elements that don't heavily overlap existing accessibility elements
        for geom in geometric_elements:
            matched_ax = False
            for ax in accessibility_elements:
                if geom.bbox.intersection_over_union(ax.bbox) > self.iou_match_threshold:
                    matched_ax = True
                    # Augment accessibility element sources
                    if PerceptionSource.IMAGE.value not in ax.sources:
                        ax.sources.append(PerceptionSource.IMAGE.value)
                    break
            if not matched_ax:
                candidate_elements.append(geom)

        # 2. Associate OCR text regions with containing or overlapping UI elements
        assigned_text_region_ids: set[str] = set()

        for elem in candidate_elements:
            contained_texts: list[TextRegion] = []
            for tr in text_regions:
                # Check if text region center is inside element bounding box or high IoU
                cx = tr.bbox.normalized_x + (tr.bbox.normalized_width / 2.0)
                cy = tr.bbox.normalized_y + (tr.bbox.normalized_height / 2.0)

                is_inside = elem.bbox.contains(cx, cy, normalized=True)
                has_overlap = elem.bbox.intersection_over_union(tr.bbox) > 0.25

                if is_inside or has_overlap:
                    contained_texts.append(tr)
                    assigned_text_region_ids.add(tr.region_id)

            if contained_texts:
                # Sort contained texts by reading order
                contained_texts.sort(key=lambda t: t.reading_order)
                elem.associated_text_ids = [t.region_id for t in contained_texts]
                elem_text = " ".join(t.text for t in contained_texts)
                if not elem.text_content:
                    elem.text_content = elem_text
                if PerceptionSource.OCR.value not in elem.sources:
                    elem.sources.append(PerceptionSource.OCR.value)

            merged_elements.append(elem)

        # 3. Any unassigned text regions become standalone TEXT UI elements
        for tr in text_regions:
            if tr.region_id not in assigned_text_region_ids:
                standalone_id = f"elem_txt_{len(merged_elements) + 1:05d}_{frame_id}"
                merged_elements.append(
                    UIElement(
                        element_id=standalone_id,
                        frame_id=frame_id,
                        element_type=UIElementType.TEXT,
                        bbox=tr.bbox,
                        confidence=tr.confidence,
                        sources=[PerceptionSource.OCR.value],
                        text_content=tr.text,
                        reading_order=tr.reading_order,
                        provenance={
                            "source_text_region_id": tr.region_id,
                            "detector": tr.source_provider,
                            "frame_id": frame_id,
                        },
                    )
                )

        # 4. Final deterministic spatial sort and reading order assignment
        ordered_elements = DeterministicReadingOrder.sort(merged_elements)
        return ordered_elements


# Alias for backward/spec compatibility
MultiSourceFusion = PerceptionFusion
