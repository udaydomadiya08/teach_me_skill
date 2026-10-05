"""UI Element detector registry and resolver."""

from typing import Optional

from teach_a_skill.core.logging import get_logger
from teach_a_skill.perception.detection.accessibility import PlatformAccessibilityDetector
from teach_a_skill.perception.detection.base import UIElementDetector
from teach_a_skill.perception.detection.geometry import GeometryDetector
from teach_a_skill.perception.detection.mock import MockUIDetector

logger = get_logger("teach_a_skill.perception.detection.registry")


def get_ui_detector(
    name: Optional[str] = None,
    use_accessibility: bool = False,
) -> UIElementDetector:
    """Resolve and return an available UI element detector."""
    if name in ("mock", "mock_detector"):
        return MockUIDetector()

    if name in ("accessibility", "accessibility_detector"):
        ax_det = PlatformAccessibilityDetector()
        if ax_det.is_available():
            return ax_det
        logger.warning("Accessibility detector requested but not available; falling back to GeometryDetector.")
        return GeometryDetector()

    if use_accessibility:
        ax_det = PlatformAccessibilityDetector()
        if ax_det.is_available():
            logger.debug("Resolved PlatformAccessibilityDetector.")
            return ax_det

    # Default screen-only geometry detector
    geom_det = GeometryDetector()
    if geom_det.is_available():
        return geom_det

    logger.warning("GeometryDetector unavailable; defaulting to MockUIDetector.")
    return MockUIDetector()
