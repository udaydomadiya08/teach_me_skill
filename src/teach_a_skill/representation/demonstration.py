"""Top-level canonical Demonstration container and entry point."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from teach_a_skill.representation.models import (
    DemonstrationManifest,
    DemonstrationSegment,
    DemonstrationSummary,
    TemporalRelation,
)
from teach_a_skill.representation.query import RepresentationQueryEngine
from teach_a_skill.representation.storage import RepresentationStorage
from teach_a_skill.representation.timeline import CanonicalTimeline
from teach_a_skill.storage.manager import StorageManager


@dataclass
class Demonstration:
    """Canonical demonstration object referencing immutable raw evidence and derived indices."""

    manifest: DemonstrationManifest
    summary: DemonstrationSummary
    timeline: CanonicalTimeline
    segments: list[DemonstrationSegment]
    relations: list[TemporalRelation]
    query_engine: RepresentationQueryEngine

    @classmethod
    def load(cls, session_id: str, storage_manager: StorageManager) -> "Demonstration":
        """Load fully instantiated Demonstration and query engine from disk."""
        query_engine = RepresentationQueryEngine(storage_manager, session_id)
        storage = RepresentationStorage(storage_manager, session_id)

        manifest = query_engine.manifest
        summary = query_engine.summary
        timeline_items = list(storage.stream_timeline_items())
        segments = list(storage.stream_segments())
        relations = list(storage.stream_relations())

        return cls(
            manifest=manifest,
            summary=summary,
            timeline=CanonicalTimeline(timeline_items),
            segments=segments,
            relations=relations,
            query_engine=query_engine,
        )

    def print_summary(self) -> None:
        """Print clean user-facing demonstration representation summary."""
        print(f"\nCanonical Demonstration Summary: {self.manifest.demonstration_id}")
        print("=============================================================")
        print(f"Recording Session:      {self.manifest.recording_session_id}")
        print(f"Teaching Session:       {self.manifest.teaching_session_id or 'None'}")
        print(f"Duration:               {self.summary.total_duration_sec:.2f}s")
        print(f"Fingerprint:            {self.manifest.fingerprint[:16]}...")
        print(f"Canonical Events:       {self.summary.total_canonical_events}")
        print(f"  • Pointer Events:     {self.summary.events_by_category.get('POINTER', 0)}")
        print(f"  • Keyboard Events:    {self.summary.events_by_category.get('KEYBOARD', 0)}")
        print(f"  • Window Events:      {self.summary.events_by_category.get('WINDOW', 0)}")
        print(f"  • Screen Checkpoints: {self.summary.events_by_category.get('SCREEN', 0)}")
        print(f"Physical Interactions:")
        print(f"  • Clicks:             {self.summary.total_click_interactions}")
        print(f"  • Double-Clicks:      {self.summary.total_double_clicks}")
        print(f"  • Drags:              {self.summary.total_drag_sequences}")
        print(f"  • Pointer Paths:      {self.summary.total_pointer_paths}")
        print(f"  • Keyboard Shortcuts: {self.summary.total_keyboard_shortcuts}")
        print(f"  • Text Sequences:     {self.summary.total_text_inputs}")
        print(f"Teaching Evidence:")
        print(f"  • Speech Segments:    {self.summary.total_speech_segments} ({self.summary.total_speech_duration_sec:.1f}s)")
        print(f"  • Annotations:        {self.summary.total_annotations}")
        print(f"Demonstration Segments: {self.summary.total_segments}")
        print(f"Temporal Relations:     {len(self.relations)}")
        print(f"Applications Involved:  {', '.join(self.summary.distinct_applications) or 'None'}")
        print(f"Idle Ratio:             {self.summary.idle_ratio * 100:.1f}% ({self.summary.idle_duration_sec:.1f}s)")
        print(f"Activity Density:       {self.summary.activity_density_events_per_sec:.2f} events/sec\n")
