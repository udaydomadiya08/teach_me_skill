"""UI element detection subsystem."""

from teach_a_skill.perception.detection.accessibility import PlatformAccessibilityDetector
from teach_a_skill.perception.detection.base import UIElementDetector
from teach_a_skill.perception.detection.geometry import GeometryDetector
from teach_a_skill.perception.detection.mock import MockUIDetector
from teach_a_skill.perception.detection.registry import get_ui_detector

__all__ = [
    "UIElementDetector",
    "GeometryDetector",
    "PlatformAccessibilityDetector",
    "MockUIDetector",
    "get_ui_detector",
]
