"""Storage partitioning, streaming serialization, and atomic promotion for canonical representations."""

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any, Generator, Optional

from teach_a_skill.core.errors import StorageError
from teach_a_skill.core.logging import get_logger
from teach_a_skill.representation.indexes import DemonstrationIndexes
from teach_a_skill.representation.models import (
    CanonicalEvent,
    DemonstrationManifest,
    DemonstrationSegment,
    DemonstrationSummary,
    TemporalRelation,
)
from teach_a_skill.representation.timeline import CanonicalTimelineItem
from teach_a_skill.storage.manager import StorageManager

logger = get_logger("teach_a_skill.representation.storage")


class RepresentationStorage:
    """Manages disk persistence and atomic publishing of canonical demonstration representations."""

    def __init__(self, storage_manager: StorageManager, recording_session_id: str) -> None:
        self.storage_manager = storage_manager
        self.recording_session_id = recording_session_id

        # Session root
        self.session_dir = self.storage_manager.get_path("recordings", recording_session_id)
        # Dedicated canonical representation directory
        self.representation_dir = self.session_dir / "representation"
        self.temp_build_dir = self.session_dir / "representation.tmp"

        # Canonical file targets
        self.manifest_file = self.representation_dir / "manifest.json"
        self.summary_file = self.representation_dir / "summary.json"
        self.timeline_file = self.representation_dir / "timeline.jsonl"
        self.segments_file = self.representation_dir / "segments.jsonl"
        self.relations_file = self.representation_dir / "relations.jsonl"
        self.checksums_file = self.representation_dir / "checksums.json"
        self.indexes_file = self.representation_dir / "indexes" / "indexes.json"
        self.events_file = self.representation_dir / "events.jsonl"
        self.interactions_dir = self.representation_dir / "interactions"

    def exists(self) -> bool:
        """True if canonical representation has been built and manifest exists."""
        return self.manifest_file.exists() and self.summary_file.exists()

    def compute_raw_evidence_checksums(
        self_or_dir: Any, session_dir: Optional[Path] = None
    ) -> dict[str, str]:
        """Compute SHA-256 hashes of all underlying Phase 2 and Phase 3 raw evidence.

        Supports both instance call: `rep_storage.compute_raw_evidence_checksums()`
        and class call: `RepresentationStorage.compute_raw_evidence_checksums(session_dir)`.
        """
        if isinstance(self_or_dir, Path):
            target_dir = self_or_dir
        elif isinstance(self_or_dir, str):
            target_dir = Path(self_or_dir)
        elif hasattr(self_or_dir, "session_dir"):
            target_dir = session_dir or self_or_dir.session_dir
        else:
            target_dir = session_dir or Path(self_or_dir)

        hashes: dict[str, str] = {}
        targets = [
            target_dir / "manifest.json",
            target_dir / "checksums.json",
            target_dir / "events" / "events.jsonl",
            target_dir / "metadata" / "frame_index.json",
            target_dir / "teaching" / "manifest.json",
            target_dir / "teaching" / "transcript.jsonl",
            target_dir / "teaching" / "annotations.jsonl",
        ]

        for target in targets:
            if target.exists() and target.is_file():
                rel_path = str(target.relative_to(target_dir))
                hashes[rel_path] = hashlib.sha256(target.read_bytes()).hexdigest()

        return hashes

    def create_temp_build_environment(self) -> Path:
        """Create a clean isolated temporary build directory."""
        if self.temp_build_dir.exists():
            shutil.rmtree(self.temp_build_dir)
        self.temp_build_dir.mkdir(parents=True, exist_ok=True)
        (self.temp_build_dir / "indexes").mkdir(parents=True, exist_ok=True)
        (self.temp_build_dir / "interactions").mkdir(parents=True, exist_ok=True)
        return self.temp_build_dir

    def write_staged_representation(
        self,
        staged_dir: Path,
        manifest: DemonstrationManifest,
        summary: DemonstrationSummary,
        timeline_items: list[CanonicalTimelineItem],
        segments: list[DemonstrationSegment],
        relations: list[TemporalRelation],
        indexes: DemonstrationIndexes,
        canonical_events: Optional[list[CanonicalEvent]] = None,
        interactions: Optional[dict[str, list[Any]]] = None,
    ) -> dict[str, str]:
        """Write all representation files into the staged directory and compute checksums."""
        # 1. Manifest & Summary
        with open(staged_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest.to_dict(), f, indent=2)

        with open(staged_dir / "summary.json", "w", encoding="utf-8") as f:
            json.dump(summary.to_dict(), f, indent=2)

        # 2. Canonical Events JSONL
        if canonical_events:
            with open(staged_dir / "events.jsonl", "w", encoding="utf-8") as f:
                for ev in canonical_events:
                    f.write(json.dumps(ev.to_dict(), separators=(",", ":")) + "\n")

        # 3. Timeline JSONL
        with open(staged_dir / "timeline.jsonl", "w", encoding="utf-8") as f:
            for item in timeline_items:
                f.write(json.dumps(item.to_dict(), separators=(",", ":")) + "\n")

        # 4. Segments JSONL
        with open(staged_dir / "segments.jsonl", "w", encoding="utf-8") as f:
            for seg in segments:
                f.write(json.dumps(seg.to_dict(), separators=(",", ":")) + "\n")

        # 5. Relations JSONL
        with open(staged_dir / "relations.jsonl", "w", encoding="utf-8") as f:
            for rel in relations:
                f.write(json.dumps(rel.to_dict(), separators=(",", ":")) + "\n")

        # 6. Derived Interactions
        if interactions:
            int_dir = staged_dir / "interactions"
            int_dir.mkdir(parents=True, exist_ok=True)
            for fname, data in interactions.items():
                with open(int_dir / fname, "w", encoding="utf-8") as f:
                    json.dump([item.to_dict() if hasattr(item, "to_dict") else item for item in data], f, indent=2)

        # 7. Indexes JSON
        indexes.save(staged_dir / "indexes" / "indexes.json")

        # 8. Event ID index map for O(1) single-event lookups
        if canonical_events:
            event_id_map: dict[str, int] = {}
            for line_num, ev in enumerate(canonical_events):
                event_id_map[ev.event_id] = line_num
                event_id_map[ev.source_event_id] = line_num
            with open(staged_dir / "event_id_map.json", "w", encoding="utf-8") as f:
                json.dump(event_id_map, f, separators=(",", ":"))

        # 9. Checksums
        checksums: dict[str, str] = {}
        for fname in ["manifest.json", "summary.json", "events.jsonl", "timeline.jsonl", "segments.jsonl", "relations.jsonl", "indexes/indexes.json"]:
            path = staged_dir / fname
            if path.exists():
                checksums[fname] = hashlib.sha256(path.read_bytes()).hexdigest()

        with open(staged_dir / "checksums.json", "w", encoding="utf-8") as f:
            json.dump(checksums, f, indent=2)

        checksums["checksums.json"] = hashlib.sha256((staged_dir / "checksums.json").read_bytes()).hexdigest()
        return checksums

    def promote_staged_representation(self, staged_dir: Path) -> None:
        """Atomically replace active representation directory with staged build."""
        backup_dir = self.session_dir / "representation.bak"
        if backup_dir.exists():
            shutil.rmtree(backup_dir)

        if self.representation_dir.exists():
            self.representation_dir.rename(backup_dir)

        try:
            staged_dir.rename(self.representation_dir)
            if backup_dir.exists():
                shutil.rmtree(backup_dir)
        except Exception as e:
            logger.error(f"Failed to promote representation, restoring backup: {e}")
            if backup_dir.exists() and not self.representation_dir.exists():
                backup_dir.rename(self.representation_dir)
            raise StorageError(f"Atomic representation promotion failed: {e}") from e

    # Streaming readers for memory-bounded querying
    def stream_canonical_events(self) -> Generator[CanonicalEvent, None, None]:
        """Stream canonical events one-by-one from disk."""
        if not self.events_file.exists():
            return
        with open(self.events_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield CanonicalEvent.from_dict(json.loads(line))

    def stream_timeline_items(self) -> Generator[CanonicalTimelineItem, None, None]:
        """Stream timeline items one-by-one from disk."""
        if not self.timeline_file.exists():
            return
        with open(self.timeline_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield CanonicalTimelineItem.from_dict(json.loads(line))

    def stream_segments(self) -> Generator[DemonstrationSegment, None, None]:
        """Stream demonstration segments one-by-one."""
        if not self.segments_file.exists():
            return
        with open(self.segments_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield DemonstrationSegment.from_dict(json.loads(line))

    def stream_relations(self) -> Generator[TemporalRelation, None, None]:
        """Stream temporal relations one-by-one."""
        if not self.relations_file.exists():
            return
        with open(self.relations_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield TemporalRelation.from_dict(json.loads(line))

    def read_derived_interactions(self, filename: str) -> list[dict[str, Any]]:
        """Read derived physical interaction records (clicks, drags, shortcuts, etc.)."""
        target = self.interactions_dir / filename
        if not target.exists():
            return []
        with open(target, "r", encoding="utf-8") as f:
            return json.load(f)

    def read_manifest(self) -> DemonstrationManifest:
        """Read manifestation metadata."""
        with open(self.manifest_file, "r", encoding="utf-8") as f:
            return DemonstrationManifest.from_dict(json.load(f))

    def read_summary(self) -> DemonstrationSummary:
        """Read summary statistics."""
        with open(self.summary_file, "r", encoding="utf-8") as f:
            return DemonstrationSummary.from_dict(json.load(f))

    def read_indexes(self) -> DemonstrationIndexes:
        """Read fast lookup indexes."""
        return DemonstrationIndexes.load(self.indexes_file)

    def read_event_id_map(self) -> dict[str, int]:
        """Load event_id -> line_number mapping for O(1) single-event lookup."""
        map_file = self.representation_dir / "event_id_map.json"
        if not map_file.exists():
            return {}
        with open(map_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def read_event_at_line(self, line_number: int) -> Optional[CanonicalEvent]:
        """Read a single canonical event by line number (0-indexed) from events.jsonl.

        Uses linecache for fast random access into the JSONL file.
        """
        import linecache
        if not self.events_file.exists():
            return None
        # linecache uses 1-indexed line numbers
        line = linecache.getline(str(self.events_file), line_number + 1)
        line = line.strip()
        if line:
            return CanonicalEvent.from_dict(json.loads(line))
        return None
