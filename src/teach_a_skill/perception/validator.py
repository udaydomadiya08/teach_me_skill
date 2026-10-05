"""Validation suite for canonical perception partitions."""

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from teach_a_skill.core.logging import get_logger
from teach_a_skill.perception.models import PerceptionManifest

logger = get_logger("teach_a_skill.perception.validator")


@dataclass
class PerceptionValidationReport:
    """Detailed report produced by PerceptionValidator."""

    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    statistics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "statistics": self.statistics,
        }


class PerceptionValidator:
    """Validates structural integrity, checksums, and frame referential completeness."""

    def __init__(self, storage_manager: Optional[Any] = None) -> None:
        self.storage_manager = storage_manager

    def validate_session(self, session_id: str) -> tuple[bool, list[str]]:
        """Validate session perception partition using stored storage_manager."""
        if self.storage_manager is None:
            raise ValueError("PerceptionValidator requires storage_manager to validate session.")
        rec_dir = self.storage_manager.get_path("recordings", session_id)
        p_dir = rec_dir / "perception"
        rep = self.validate_perception(p_dir, raw_session_dir=rec_dir)
        return rep.is_valid, rep.errors

    @staticmethod
    def validate_perception(
        perception_dir: Path,
        raw_session_dir: Optional[Path] = None,
    ) -> PerceptionValidationReport:
        """Validate an on-disk perception partition."""
        errors: list[str] = []
        warnings: list[str] = []
        stats: dict[str, Any] = {}

        manifest_file = perception_dir / "manifest.json"
        frames_file = perception_dir / "frames.jsonl"
        elements_file = perception_dir / "elements.jsonl"
        text_regions_file = perception_dir / "text_regions.jsonl"
        ocr_results_file = perception_dir / "ocr_results.jsonl"
        checksums_file = perception_dir / "checksums.json"

        # 1. Mandatory files presence
        for req_file, name in [
            (manifest_file, "manifest.json"),
            (frames_file, "frames.jsonl"),
            (elements_file, "elements.jsonl"),
            (text_regions_file, "text_regions.jsonl"),
            (ocr_results_file, "ocr_results.jsonl"),
            (checksums_file, "checksums.json"),
        ]:
            if not req_file.exists():
                errors.append(f"Missing mandatory perception file: {name}")

        if errors:
            return PerceptionValidationReport(is_valid=False, errors=errors)

        # 2. Validate manifest and schema version
        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                manifest_data = json.load(f)
            manifest = PerceptionManifest.from_dict(manifest_data)
            stats["perception_id"] = manifest.perception_id
            stats["schema_version"] = manifest.schema_version
            stats["total_frames"] = manifest.total_frames_processed
            stats["total_elements"] = manifest.total_elements
            stats["total_text_regions"] = manifest.total_text_regions

            if manifest.schema_version != "1.0.0":
                errors.append(f"Unsupported schema version '{manifest.schema_version}' (expected 1.0.0)")
        except Exception as e:
            errors.append(f"Error reading perception manifest: {e}")

        # 3. Checksum verification across perception files
        try:
            with open(checksums_file, "r", encoding="utf-8") as f:
                checksums = json.load(f)

            for fname, expected_hash in checksums.items():
                target = perception_dir / fname
                if not target.exists():
                    errors.append(f"File listed in checksums not found: {fname}")
                    continue
                actual_hash = hashlib.sha256(target.read_bytes()).hexdigest()
                if actual_hash != expected_hash:
                    errors.append(f"Checksum mismatch for '{fname}': expected {expected_hash}, got {actual_hash}")
        except Exception as e:
            errors.append(f"Error checking integrity checksums: {e}")

        # 4. Referential integrity with raw session frames
        if raw_session_dir and raw_session_dir.exists():
            frame_index_file = raw_session_dir / "metadata" / "frame_index.json"
            if frame_index_file.exists():
                try:
                    with open(frame_index_file, "r", encoding="utf-8") as f:
                        frame_index = json.load(f)
                    raw_frame_ids = {rf["frame_id"] for rf in frame_index.get("frames", [])}

                    # Check each perception frame corresponds to a raw frame
                    with open(frames_file, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                pf_data = json.loads(line)
                                fid = pf_data.get("frame_id")
                                if fid not in raw_frame_ids:
                                    errors.append(f"Perception frame '{fid}' does not exist in raw frame index")
                except Exception as e:
                    errors.append(f"Error verifying raw frame referential integrity: {e}")

        is_valid = len(errors) == 0
        return PerceptionValidationReport(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            statistics=stats,
        )
