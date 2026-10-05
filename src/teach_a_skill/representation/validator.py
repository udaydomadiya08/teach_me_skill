"""Validation suite for canonical demonstration representations."""

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from teach_a_skill.core.logging import get_logger
from teach_a_skill.representation.models import DemonstrationManifest

logger = get_logger("teach_a_skill.representation.validator")


@dataclass
class ValidationReport:
    """Detailed report produced by RepresentationValidator."""

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


class RepresentationValidator:
    """Validates structural integrity, referential completeness, and timestamp monotonicity."""

    @staticmethod
    def validate_representation(
        representation_dir: Path,
        raw_session_dir: Optional[Path] = None,
    ) -> ValidationReport:
        """Validate an on-disk canonical representation partition."""
        errors: list[str] = []
        warnings: list[str] = []
        stats: dict[str, Any] = {}

        manifest_file = representation_dir / "manifest.json"
        summary_file = representation_dir / "summary.json"
        timeline_file = representation_dir / "timeline.jsonl"
        segments_file = representation_dir / "segments.jsonl"
        relations_file = representation_dir / "relations.jsonl"
        checksums_file = representation_dir / "checksums.json"

        # 1. Mandatory files presence
        for req_file, name in [
            (manifest_file, "manifest.json"),
            (summary_file, "summary.json"),
            (timeline_file, "timeline.jsonl"),
            (segments_file, "segments.jsonl"),
            (relations_file, "relations.jsonl"),
            (checksums_file, "checksums.json"),
        ]:
            if not req_file.exists():
                errors.append(f"Missing mandatory representation file: {name}")

        if errors:
            return ValidationReport(is_valid=False, errors=errors)

        # 2. Validate manifest and schema version
        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                manifest_data = json.load(f)
            manifest = DemonstrationManifest.from_dict(manifest_data)
            stats["demonstration_id"] = manifest.demonstration_id
            stats["schema_version"] = manifest.schema_version
            if manifest.schema_version != "1.0.0":
                errors.append(f"Unsupported schema version '{manifest.schema_version}' (expected 1.0.0)")
            if not manifest.fingerprint:
                errors.append("Manifest missing cryptographic fingerprint")
        except Exception as e:
            errors.append(f"Error parsing manifest.json: {e}")

        # 3. Checksum integrity verification
        try:
            with open(checksums_file, "r", encoding="utf-8") as f:
                checksums = json.load(f)

            for fname, expected_hash in checksums.items():
                target = representation_dir / fname
                if not target.exists():
                    errors.append(f"File listed in checksums not found: {fname}")
                    continue
                actual_hash = hashlib.sha256(target.read_bytes()).hexdigest()
                if actual_hash != expected_hash:
                    errors.append(f"Checksum mismatch for {fname}: expected {expected_hash}, got {actual_hash}")
        except Exception as e:
            errors.append(f"Error checking integrity checksums: {e}")

        # 4. Timeline items monotonicity and uniqueness
        timeline_item_ids: set[str] = set()
        last_mono_ns = -1
        timeline_count = 0

        try:
            with open(timeline_file, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    item = json.loads(line)
                    timeline_count += 1
                    item_id = item.get("item_id", "")
                    if not item_id:
                        errors.append(f"Timeline item at line {line_num} missing item_id")
                        continue
                    if item_id in timeline_item_ids:
                        errors.append(f"Duplicate timeline item_id '{item_id}' at line {line_num}")
                    timeline_item_ids.add(item_id)

                    mono_ns = item.get("monotonic_timestamp_ns", 0)
                    if mono_ns < last_mono_ns:
                        errors.append(
                            f"Monotonic timestamp ordering violation at line {line_num}: "
                            f"{mono_ns} < {last_mono_ns}"
                        )
                    last_mono_ns = mono_ns

            stats["timeline_items_count"] = timeline_count
        except Exception as e:
            errors.append(f"Error validating timeline.jsonl: {e}")

        # 5. Segments validity
        segment_count = 0
        try:
            with open(segments_file, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    seg = json.loads(line)
                    segment_count += 1
                    seg_id = seg.get("segment_id", "")
                    if not seg_id:
                        errors.append(f"Segment at line {line_num} missing segment_id")
                    if seg.get("start_monotonic_ns", 0) > seg.get("end_monotonic_ns", 0):
                        errors.append(f"Segment {seg_id} start > end timestamp")
            stats["segments_count"] = segment_count
        except Exception as e:
            errors.append(f"Error validating segments.jsonl: {e}")

        # 6. Relations validity
        relation_count = 0
        try:
            with open(relations_file, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    rel = json.loads(line)
                    relation_count += 1
                    if not rel.get("source_id") or not rel.get("target_id"):
                        errors.append(f"Relation at line {line_num} missing source or target ID")
            stats["relations_count"] = relation_count
        except Exception as e:
            errors.append(f"Error validating relations.jsonl: {e}")

        return ValidationReport(
            is_valid=(len(errors) == 0),
            errors=errors,
            warnings=warnings,
            statistics=stats,
        )
