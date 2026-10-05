"""Phase 5: Local UI Perception and OCR Subsystem."""

from teach_a_skill.perception.models import (
    BoundingBox,
    OCRResult,
    PerceptionFrame,
    PerceptionManifest,
    PerceptionMode,
    PerceptionSource,
    TextRegion,
    UIElement,
    UIElementType,
    VisualRegion,
)
from teach_a_skill.perception.pipeline import PerceptionPipeline
from teach_a_skill.perception.query import PerceptionQueryEngine
from teach_a_skill.perception.storage import PerceptionStorage
from teach_a_skill.perception.validator import PerceptionValidationReport, PerceptionValidator

__all__ = [
    "UIElementType",
    "PerceptionSource",
    "PerceptionMode",
    "BoundingBox",
    "TextRegion",
    "UIElement",
    "OCRResult",
    "VisualRegion",
    "PerceptionFrame",
    "PerceptionManifest",
    "PerceptionPipeline",
    "PerceptionStorage",
    "PerceptionQueryEngine",
    "PerceptionValidator",
    "PerceptionValidationReport",
]
