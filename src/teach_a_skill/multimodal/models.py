"""Canonical data models for Phase 6: Local Multimodal Intelligence."""

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional, Union

from teach_a_skill.perception.models import BoundingBox


class ObservationType(str, Enum):
    """Taxonomy of factual, multimodal visible and physical observations.
    
    CRITICAL: Strictly describes WHAT WAS VISIBLY OR PHYSICALLY PRESENT,
    never user goals, intent, task semantics, or action recommendations.
    """

    # Visual & Structural
    VISIBLE_TEXT = "VISIBLE_TEXT"
    VISIBLE_UI_ELEMENT = "VISIBLE_UI_ELEMENT"
    PERSISTENT_REGION = "PERSISTENT_REGION"
    TEXT_CHANGE = "TEXT_CHANGE"
    REGION_CHANGE = "REGION_CHANGE"
    UI_CHANGE = "UI_CHANGE"

    # Spatial & Pointer
    POINTER_PROXIMITY = "POINTER_PROXIMITY"
    POINTER_CLICK_TARGET = "POINTER_CLICK_TARGET"
    KEYBOARD_TARGET = "KEYBOARD_TARGET"

    # Application & Environment
    WINDOW_STATE = "WINDOW_STATE"
    APPLICATION_STATE = "APPLICATION_STATE"

    # Multimodal Corroboration & Speech
    SPEECH_PRESENT = "SPEECH_PRESENT"
    ANNOTATION_PRESENT = "ANNOTATION_PRESENT"
    CROSS_MODAL_MATCH = "CROSS_MODAL_MATCH"
    CROSS_MODAL_CONFLICT = "CROSS_MODAL_CONFLICT"
    TEMPORAL_TRANSITION = "TEMPORAL_TRANSITION"

    def __str__(self) -> str:
        return self.value


class ModalityType(str, Enum):
    """Source modalities contributing evidence to observations."""

    SCREEN_FRAME = "SCREEN_FRAME"
    CANONICAL_EVENT = "CANONICAL_EVENT"
    OCR_TEXT = "OCR_TEXT"
    UI_ELEMENT = "UI_ELEMENT"
    SPEECH_TRANSCRIPT = "SPEECH_TRANSCRIPT"
    TYPED_ANNOTATION = "TYPED_ANNOTATION"
    WINDOW_CONTEXT = "WINDOW_CONTEXT"
    POINTER = "POINTER"
    KEYBOARD = "KEYBOARD"

    def __str__(self) -> str:
        return self.value


@dataclass
class MultimodalEvidenceRef:
    """Explicit traceable reference back to authoritative Phase 2-5 evidence."""

    evidence_type: str  # e.g., "canonical_event", "ocr_region", "frame", "transcript"
    evidence_id: str    # e.g., "cevt_0001", "tr_0002", "frame_000001", "seg_0001"
    modality: str       # ModalityType value
    timestamp_ns: int
    relative_time_ms: float
    bounding_box: Optional[BoundingBox] = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.bounding_box:
            d["bounding_box"] = self.bounding_box.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MultimodalEvidenceRef":
        data_copy = dict(data)
        if isinstance(data_copy.get("bounding_box"), dict):
            data_copy["bounding_box"] = BoundingBox.from_dict(data_copy["bounding_box"])
        return cls(**data_copy)


@dataclass
class MultimodalObservation:
    """Structured, grounded multimodal observation.
    
    Describes concrete co-occurrences of visual elements, physical events,
    speech, and window context without semantic or intentional inference.
    """

    observation_id: str
    session_id: str
    observation_type: ObservationType
    description: str
    timestamp_ns: int
    relative_time_ms: float
    duration_ms: float = 0.0
    evidence_refs: list[MultimodalEvidenceRef] = field(default_factory=list)
    supporting_modalities: list[str] = field(default_factory=list)
    contradicting_modalities: list[str] = field(default_factory=list)
    confidence: float = 1.0
    uncertainty_reason: Optional[str] = None
    provider: str = "deterministic"
    model_id: str = "deterministic_rules"
    model_version: str = "1.0.0"
    created_at: str = ""
    schema_version: str = "1.0.0"
    fingerprint: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)
    grounded: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "session_id": self.session_id,
            "observation_type": self.observation_type.value if hasattr(self.observation_type, "value") else str(self.observation_type),
            "description": self.description,
            "timestamp_ns": self.timestamp_ns,
            "relative_time_ms": self.relative_time_ms,
            "duration_ms": self.duration_ms,
            "evidence_refs": [ref.to_dict() for ref in self.evidence_refs],
            "supporting_modalities": list(self.supporting_modalities),
            "contradicting_modalities": list(self.contradicting_modalities),
            "confidence": round(self.confidence, 4),
            "uncertainty_reason": self.uncertainty_reason,
            "provider": self.provider,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "created_at": self.created_at,
            "schema_version": self.schema_version,
            "fingerprint": self.fingerprint,
            "provenance": dict(self.provenance),
            "grounded": self.grounded,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MultimodalObservation":
        data_copy = dict(data)
        data_copy["observation_type"] = ObservationType(data_copy["observation_type"])
        data_copy["evidence_refs"] = [
            MultimodalEvidenceRef.from_dict(r) for r in data_copy.get("evidence_refs", [])
        ]
        return cls(**data_copy)


@dataclass
class TemporalWindow:
    """Bounded temporal slice aggregating cross-modal evidence for analysis."""

    window_id: str
    session_id: str
    start_time_ms: float
    end_time_ms: float
    start_timestamp_ns: int
    end_timestamp_ns: int
    trigger_event_id: Optional[str] = None
    canonical_event_ids: list[str] = field(default_factory=list)
    frame_ids: list[str] = field(default_factory=list)
    ocr_region_ids: list[str] = field(default_factory=list)
    ui_element_ids: list[str] = field(default_factory=list)
    transcript_segment_ids: list[str] = field(default_factory=list)
    annotation_ids: list[str] = field(default_factory=list)
    active_application: Optional[str] = None
    active_window_title: Optional[str] = None
    pointer_coordinates: Optional[tuple[float, float]] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TemporalWindow":
        return cls(**data)


@dataclass
class MultimodalManifest:
    """Summary manifest and integrity ledger for the multimodal partition."""

    manifest_id: str
    session_id: str
    schema_version: str = "1.0.0"
    derivation_version: str = "phase6-v1"
    config_hash: str = ""
    provider_id: str = "deterministic"
    model_id: str = "deterministic_rules"
    total_windows: int = 0
    total_observations: int = 0
    observation_counts_by_type: dict[str, int] = field(default_factory=dict)
    cache_hit_count: int = 0
    processing_duration_sec: float = 0.0
    source_checksums: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MultimodalManifest":
        return cls(**data)
