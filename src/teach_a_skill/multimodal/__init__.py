"""Phase 6: Local Multimodal Intelligence layer."""

from teach_a_skill.multimodal.benchmark import MultimodalBenchmarkRunner
from teach_a_skill.multimodal.cache import MultimodalCache
from teach_a_skill.multimodal.context import MultimodalContext, MultimodalContextBuilder
from teach_a_skill.multimodal.fusion import MultimodalFusionEngine
from teach_a_skill.multimodal.grounding import MultimodalGroundingEngine
from teach_a_skill.multimodal.models import (
    ModalityType,
    MultimodalEvidenceRef,
    MultimodalManifest,
    MultimodalObservation,
    ObservationType,
    TemporalWindow,
)
from teach_a_skill.multimodal.pipeline import MultimodalPipeline
from teach_a_skill.multimodal.query import MultimodalQueryEngine
from teach_a_skill.multimodal.validator import MultimodalValidator

__all__ = [
    "ObservationType",
    "ModalityType",
    "MultimodalEvidenceRef",
    "MultimodalObservation",
    "TemporalWindow",
    "MultimodalManifest",
    "MultimodalContext",
    "MultimodalContextBuilder",
    "MultimodalGroundingEngine",
    "MultimodalFusionEngine",
    "MultimodalCache",
    "MultimodalPipeline",
    "MultimodalQueryEngine",
    "MultimodalValidator",
    "MultimodalBenchmarkRunner",
]
