"""Deterministic spatial reading order algorithm."""

from typing import Sequence, TypeVar, Union

from teach_a_skill.perception.models import TextRegion, UIElement

T = TypeVar("T", TextRegion, UIElement)


class DeterministicReadingOrder:
    """Sorts text regions and UI elements in a deterministic spatial reading order."""

    @staticmethod
    def sort(items: Sequence[T], band_tolerance_px: float = 12.0) -> list[T]:
        """Sort items top-to-bottom, left-to-right, with deterministic ID tie-breaking.

        Args:
            items: Sequence of TextRegion or UIElement objects.
            band_tolerance_px: Vertical grouping tolerance in pixels.

        Returns:
            A new list of items ordered deterministically with updated reading_order values.
        """
        if not items:
            return []

        def sort_key(item: Union[TextRegion, UIElement]) -> tuple[float, float, str]:
            bbox = item.bbox
            # Quantize vertical position into bands to handle baseline jitter
            quantized_y = round(bbox.y / band_tolerance_px) * band_tolerance_px
            item_id = item.region_id if isinstance(item, TextRegion) else item.element_id
            return (quantized_y, bbox.x, item_id)

        sorted_items = sorted(items, key=sort_key)

        # Re-assign reading_order indices
        result: list[T] = []
        for idx, it in enumerate(sorted_items):
            it.reading_order = idx + 1
            result.append(it)

        return result


def sort_elements_reading_order(
    elements: Sequence[UIElement], y_band_tolerance: float = 12.0
) -> list[UIElement]:
    """Convenience helper to sort UIElements in reading order."""
    return DeterministicReadingOrder.sort(elements, band_tolerance_px=y_band_tolerance)


def sort_text_regions_reading_order(
    text_regions: Sequence[TextRegion], y_band_tolerance: float = 12.0
) -> list[TextRegion]:
    """Convenience helper to sort TextRegions in reading order."""
    return DeterministicReadingOrder.sort(text_regions, band_tolerance_px=y_band_tolerance)
