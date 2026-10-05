"""Isolated local storage manager for Phase 5 perception artifacts."""

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Iterator, Optional

from teach_a_skill.core.errors import StorageError
from teach_a_skill.core.logging import get_logger
from teach_a_skill.perception.models import (
    OCRResult,
    PerceptionFrame,
    PerceptionManifest,
    TextRegion,
    UIElement,
)
from teach_a_skill.storage.manager import StorageManager

logger = get_logger("teach_a_skill.perception.storage")


class PerceptionStorage:
    """Manages persistence, streaming JSONL serialization, and checksums for perception data."""

    def __init__(self, storage_manager: StorageManager, session_id: str) -> None:
        self.storage_manager = storage_manager
        self.session_id = session_id

        # Authoritative partition: recordings/{session_id}/perception/
        self.session_dir = storage_manager.get_path("recordings", session_id)
        self.perception_dir = self.session_dir / "perception"
        self.manifest_file = self.perception_dir / "manifest.json"
        self.frames_file = self.perception_dir / "frames.jsonl"
        self.elements_file = self.perception_dir / "elements.jsonl"
        self.text_regions_file = self.perception_dir / "text_regions.jsonl"
        self.ocr_results_file = self.perception_dir / "ocr_results.jsonl"
        self.checksums_file = self.perception_dir / "checksums.json"
        self.indexes_dir = self.perception_dir / "indexes"

    def exists(self) -> bool:
        """Return True if complete canonical perception partition exists."""
        return (
            self.perception_dir.exists()
            and self.manifest_file.exists()
            and self.frames_file.exists()
            and self.checksums_file.exists()
        )

    def create_temp_build_environment(self) -> Path:
        """Create a clean staging directory for atomic promotion."""
        staging_dir = self.session_dir / ".perception_staging"
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        staging_dir.mkdir(parents=True, exist_ok=True)
        (staging_dir / "indexes").mkdir(parents=True, exist_ok=True)
        return staging_dir

    def cleanup_staging(self) -> None:
        """Clean up any leftover temporary staging directory."""
        staging_dir = self.session_dir / ".perception_staging"
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)

    def write_staged_perception(
        self,
        staged_dir: Path,
        manifest: PerceptionManifest,
        frames: list[PerceptionFrame],
        elements: list[UIElement],
        text_regions: list[TextRegion],
        ocr_results: list[OCRResult],
        indexes: dict[str, Any],
    ) -> Path:
        """Serialize perception partition to staging and atomically promote to perception/."""
        # 1. frames.jsonl
        with open(staged_dir / "frames.jsonl", "w", encoding="utf-8") as f:
            for fr in frames:
                f.write(json.dumps(fr.to_dict(), separators=(",", ":")) + "\n")

        # 2. elements.jsonl
        with open(staged_dir / "elements.jsonl", "w", encoding="utf-8") as f:
            for el in elements:
                f.write(json.dumps(el.to_dict(), separators=(",", ":")) + "\n")

        # 3. text_regions.jsonl
        with open(staged_dir / "text_regions.jsonl", "w", encoding="utf-8") as f:
            for tr in text_regions:
                f.write(json.dumps(tr.to_dict(), separators=(",", ":")) + "\n")

        # 4. ocr_results.jsonl
        with open(staged_dir / "ocr_results.jsonl", "w", encoding="utf-8") as f:
            for ocr in ocr_results:
                f.write(json.dumps(ocr.to_dict(), separators=(",", ":")) + "\n")

        # 5. indexes/perception_index.json
        idx_dir = staged_dir / "indexes"
        idx_dir.mkdir(parents=True, exist_ok=True)
        with open(idx_dir / "perception_index.json", "w", encoding="utf-8") as f:
            json.dump(indexes, f, separators=(",", ":"))

        # 6. manifest.json
        with open(staged_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest.to_dict(), f, indent=2)

        # 7. Checksums across all produced perception files
        checksums: dict[str, str] = {}
        for child in staged_dir.rglob("*"):
            if child.is_file() and child.name != "checksums.json":
                rel = child.relative_to(staged_dir).as_posix()
                checksums[rel] = hashlib.sha256(child.read_bytes()).hexdigest()

        with open(staged_dir / "checksums.json", "w", encoding="utf-8") as f:
            json.dump(checksums, f, indent=2)

        # Atomic promotion
        if self.perception_dir.exists():
            shutil.rmtree(self.perception_dir, ignore_errors=True)

        staged_dir.rename(self.perception_dir)
        return self.perception_dir

    def read_manifest(self) -> PerceptionManifest:
        """Load PerceptionManifest."""
        if not self.manifest_file.exists():
            raise StorageError(f"Perception manifest not found at {self.manifest_file}")
        with open(self.manifest_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return PerceptionManifest.from_dict(data)

    def read_indexes(self) -> dict[str, Any]:
        """Load perception indexes."""
        idx_file = self.indexes_dir / "perception_index.json"
        if not idx_file.exists():
            return {}
        with open(idx_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def stream_frames(self) -> Iterator[PerceptionFrame]:
        """Stream PerceptionFrame objects line by line."""
        if not self.frames_file.exists():
            return
        with open(self.frames_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield PerceptionFrame.from_dict(json.loads(line))

    def stream_elements(self) -> Iterator[UIElement]:
        """Stream UIElement objects line by line."""
        if not self.elements_file.exists():
            return
        with open(self.elements_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield UIElement.from_dict(json.loads(line))

    def stream_text_regions(self) -> Iterator[TextRegion]:
        """Stream TextRegion objects line by line."""
        if not self.text_regions_file.exists():
            return
        with open(self.text_regions_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield TextRegion.from_dict(json.loads(line))

    def stream_ocr_results(self) -> Iterator[OCRResult]:
        """Stream OCRResult objects line by line."""
        if not self.ocr_results_file.exists():
            return
        with open(self.ocr_results_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield OCRResult.from_dict(json.loads(line))
