"""Canonical perception data models, UI element taxonomy, and structured OCR types."""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class UIElementType(str, Enum):
    """Structural/visual category of a detected UI region without semantic intent."""

    TEXT = "TEXT"
    BUTTON_LIKE = "BUTTON_LIKE"
    INPUT_LIKE = "INPUT_LIKE"
    CHECKBOX_LIKE = "CHECKBOX_LIKE"
    RADIO_LIKE = "RADIO_LIKE"
    DROPDOWN_LIKE = "DROPDOWN_LIKE"
    ICON_LIKE = "ICON_LIKE"
    IMAGE = "IMAGE"
    PANEL = "PANEL"
    WINDOW_REGION = "WINDOW_REGION"
    CONTAINER = "CONTAINER"
    UNKNOWN_REGION = "UNKNOWN_REGION"

    def __str__(self) -> str:
        return self.value


class PerceptionSource(str, Enum):
    """Origin detector for a perception artifact."""

    IMAGE = "IMAGE"
    ACCESSIBILITY = "ACCESSIBILITY"
    OCR = "OCR"
    HYBRID = "HYBRID"

    def __str__(self) -> str:
        return self.value


class PerceptionMode(str, Enum):
    """Perception operational mode based on platform capabilities."""

    SCREEN_ONLY = "SCREEN_ONLY"
    SCREEN_AND_ACCESSIBILITY = "SCREEN_AND_ACCESSIBILITY"

    def __str__(self) -> str:
        return self.value


@dataclass
class BoundingBox:
    """Normalized [0, 1] and pixel coordinate region of a visual artifact."""

    x: float
    y: float
    width: float
    height: float
    normalized_x: float
    normalized_y: float
    normalized_width: float
    normalized_height: float
    frame_width: int = 1920
    frame_height: int = 1080
    display_id: Optional[str] = None
    scale_factor: float = 1.0

    @property
    def x_max(self) -> float:
        return self.x + self.width

    @property
    def y_max(self) -> float:
        return self.y + self.height

    @property
    def norm_x_max(self) -> float:
        return self.normalized_x + self.normalized_width

    @property
    def x2(self) -> float:
        return self.x + self.width

    @property
    def y2(self) -> float:
        return self.y + self.height

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def norm_y_max(self) -> float:
        return self.normalized_y + self.normalized_height

    def contains(self, px: float, py: float, normalized: bool = False) -> bool:
        """Check if point is inside this bounding box."""
        if normalized:
            return (
                self.normalized_x <= px <= self.norm_x_max
                and self.normalized_y <= py <= self.norm_y_max
            )
        return self.x <= px <= self.x_max and self.y <= py <= self.y_max

    def contains_point(self, px: float, py: float, normalized: bool = False) -> bool:
        """Alias for contains."""
        return self.contains(px, py, normalized=normalized)

    def iou(self, other: "BoundingBox") -> float:
        """Alias for intersection_over_union."""
        return self.intersection_over_union(other)

    def intersection_over_union(self, other: "BoundingBox") -> float:
        """Calculate spatial Intersection over Union (IoU) in normalized space."""
        x1 = max(self.normalized_x, other.normalized_x)
        y1 = max(self.normalized_y, other.normalized_y)
        x2 = min(self.norm_x_max, other.norm_x_max)
        y2 = min(self.norm_y_max, other.norm_y_max)

        inter_w = max(0.0, x2 - x1)
        inter_h = max(0.0, y2 - y1)
        inter_area = inter_w * inter_h

        if inter_area == 0.0:
            return 0.0

        area1 = self.normalized_width * self.normalized_height
        area2 = other.normalized_width * other.normalized_height
        union_area = area1 + area2 - inter_area
        return inter_area / union_area if union_area > 0.0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BoundingBox":
        return cls(**data)


@dataclass
class TextRegion:
    """Localized OCR text segment with confidence and deterministic reading order."""

    region_id: str
    frame_id: str
    text: str
    raw_text: str
    normalized_text: str
    bbox: BoundingBox
    confidence: Optional[float] = None
    language: Optional[str] = None
    line_id: Optional[str] = None
    word_ids: list[str] = field(default_factory=list)
    reading_order: int = 0
    source_provider: str = "ocr"
    source: Optional[Any] = None
    provenance: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.source is not None:
            self.source_provider = self.source.value if hasattr(self.source, "value") else str(self.source)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["bbox"] = self.bbox.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TextRegion":
        data_copy = dict(data)
        if isinstance(data_copy.get("bbox"), dict):
            data_copy["bbox"] = BoundingBox.from_dict(data_copy["bbox"])
        return cls(**data_copy)


@dataclass
class UIElement:
    """Structural visible or accessible UI component."""

    element_id: str
    frame_id: str
    element_type: UIElementType
    bbox: BoundingBox
    confidence: Optional[float] = None
    sources: list[str] = field(default_factory=lambda: [PerceptionSource.IMAGE.value])
    text_content: Optional[str] = None
    associated_text_ids: list[str] = field(default_factory=list)
    accessibility_attributes: dict[str, Any] = field(default_factory=dict)
    reading_order: int = 0
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "element_id": self.element_id,
            "frame_id": self.frame_id,
            "element_type": self.element_type.value if hasattr(self.element_type, "value") else str(self.element_type),
            "bbox": self.bbox.to_dict(),
            "confidence": self.confidence,
            "sources": [s.value if hasattr(s, "value") else str(s) for s in self.sources],
            "text_content": self.text_content,
            "associated_text_ids": list(self.associated_text_ids),
            "accessibility_attributes": dict(self.accessibility_attributes),
            "reading_order": self.reading_order,
            "provenance": dict(self.provenance),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UIElement":
        data_copy = dict(data)
        if isinstance(data_copy.get("bbox"), dict):
            data_copy["bbox"] = BoundingBox.from_dict(data_copy["bbox"])
        data_copy["element_type"] = UIElementType(data_copy["element_type"])
        return cls(**data_copy)


@dataclass
class OCRResult:
    """Consolidated raw OCR extraction for a single screen checkpoint frame."""

    ocr_id: str
    frame_id: str
    provider_id: str
    provider_version: str
    text_regions: list[TextRegion] = field(default_factory=list)
    raw_full_text: str = ""
    confidence_aggregate: Optional[float] = None
    timing_ms: float = 0.0
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ocr_id": self.ocr_id,
            "frame_id": self.frame_id,
            "provider_id": self.provider_id,
            "provider_version": self.provider_version,
            "text_regions": [r.to_dict() for r in self.text_regions],
            "raw_full_text": self.raw_full_text,
            "confidence_aggregate": self.confidence_aggregate,
            "timing_ms": self.timing_ms,
            "provenance": dict(self.provenance),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OCRResult":
        data_copy = dict(data)
        if "text_regions" in data_copy:
            data_copy["text_regions"] = [
                TextRegion.from_dict(r) if isinstance(r, dict) else r
                for r in data_copy["text_regions"]
            ]
        return cls(**data_copy)


@dataclass
class VisualRegion:
    """Coarse visual or geometric partition of a frame."""

    region_id: str
    frame_id: str
    bbox: BoundingBox
    region_type: str  # e.g., "window_container", "dialog", "toolbar", "content_area"
    confidence: Optional[float] = None
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["bbox"] = self.bbox.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VisualRegion":
        data_copy = dict(data)
        if isinstance(data_copy.get("bbox"), dict):
            data_copy["bbox"] = BoundingBox.from_dict(data_copy["bbox"])
        return cls(**data_copy)


@dataclass
class PerceptionFrame:
    """Perception checkpoint associated with a Phase 2 authoritative frame."""

    perception_frame_id: str
    frame_id: str
    session_id: str
    timestamp_ns: int
    relative_time_ms: float
    frame_path: str
    frame_checksum: str
    frame_width: int
    frame_height: int
    scale_factor: float = 1.0
    mode: str = PerceptionMode.SCREEN_ONLY.value
    elements_count: int = 0
    text_regions_count: int = 0
    processing_time_ms: float = 0.0
    cache_hit: bool = False
    config_hash: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PerceptionFrame":
        return cls(**data)


@dataclass
class PerceptionManifest:
    """Authoritative metadata manifest for a session perception partition."""

    perception_id: str
    session_id: str
    schema_version: str = "1.0.0"
    derivation_version: str = "phase5-v1"
    config_hash: str = ""
    ocr_provider: str = ""
    detector_provider: str = ""
    mode: str = PerceptionMode.SCREEN_ONLY.value
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    total_frames_processed: int = 0
    total_elements: int = 0
    total_text_regions: int = 0
    cache_hit_count: int = 0
    processing_duration_sec: float = 0.0
    source_frame_checksums: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PerceptionManifest":
        return cls(**data)
