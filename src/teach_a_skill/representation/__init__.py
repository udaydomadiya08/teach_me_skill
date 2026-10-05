"""Phase 4 Canonical Demonstration Representation Layer."""

from teach_a_skill.representation.benchmark import (
    RepresentationBenchmarkReport,
    run_representation_benchmark,
)
from teach_a_skill.representation.builder import RepresentationBuilder
from teach_a_skill.representation.demonstration import Demonstration
from teach_a_skill.representation.models import (
    ApplicationTransition,
    CanonicalEvent,
    CanonicalEventType,
    ClickInteraction,
    DemonstrationContext,
    DemonstrationManifest,
    DemonstrationSegment,
    DemonstrationSummary,
    DoubleClickInteraction,
    DragSequence,
    EventCategory,
    IdleInterval,
    KeyboardShortcutSequence,
    PointerPath,
    TemporalRelation,
    TemporalRelationType,
    TextInputSequence,
    WindowContextInterval,
)
from teach_a_skill.representation.query import RepresentationQueryEngine
from teach_a_skill.representation.storage import RepresentationStorage
from teach_a_skill.representation.timeline import (
    CanonicalTimeline,
    CanonicalTimelineItem,
    TimelineItemType,
)
from teach_a_skill.representation.validator import (
    RepresentationValidator,
    ValidationReport,
)

__all__ = [
    "Demonstration",
    "RepresentationBuilder",
    "RepresentationQueryEngine",
    "RepresentationStorage",
    "RepresentationValidator",
    "ValidationReport",
    "CanonicalEvent",
    "CanonicalEventType",
    "EventCategory",
    "ClickInteraction",
    "DoubleClickInteraction",
    "DragSequence",
    "PointerPath",
    "KeyboardShortcutSequence",
    "TextInputSequence",
    "IdleInterval",
    "WindowContextInterval",
    "ApplicationTransition",
    "TemporalRelation",
    "TemporalRelationType",
    "DemonstrationSegment",
    "DemonstrationSummary",
    "DemonstrationManifest",
    "DemonstrationContext",
    "CanonicalTimeline",
    "CanonicalTimelineItem",
    "TimelineItemType",
    "run_representation_benchmark",
    "RepresentationBenchmarkReport",
]
