"""Validator for Phase 6 multimodal artifacts, schema, provenance, and semantic boundaries."""

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Optional

from teach_a_skill.core.logging import get_logger
from teach_a_skill.multimodal.models import MultimodalObservation
from teach_a_skill.multimodal.storage import MultimodalStorage
from teach_a_skill.storage.manager import StorageManager

logger = get_logger("teach_a_skill.multimodal.validator")

PROHIBITED_BOUNDARY_TERMS = [
    r"\buser(?:\'s)?\s+(?:intent|goal|objective|desire|plan)\b",
    r"\b(?:wants?|trying|attempting)\s+to\b",
    r"\btask\s+(?:goal|decomposition|plan)\b",
    r"\bskill\s+(?:compilation|execution|procedure)\b",
    r"\bnext\s+action\s+should\s+be\b",
    r"\baction\s+plan\b",
    r"\bautomation\s+plan\b",
    r"\bdesired\s+outcome\b",
]
_BOUNDARY_REGEX = re.compile("|".join(PROHIBITED_BOUNDARY_TERMS), re.IGNORECASE)


class MultimodalValidator:
    """Validates schema conformance, provenance, integrity, and strict semantic boundaries."""

    def __init__(self, storage_manager: StorageManager) -> None:
        self.storage_manager = storage_manager

    def validate_session(self, session_id: str) -> dict[str, Any]:
        """Perform comprehensive validation on Phase 6 multimodal artifacts."""
        storage = MultimodalStorage(self.storage_manager, session_id)
        mm_dir = storage.multimodal_dir

        errors: list[str] = []
        warnings: list[str] = []

        if not storage.exists():
            return {
                "valid": False,
                "session_id": session_id,
                "errors": [f"Multimodal artifacts missing for session {session_id}"],
                "warnings": [],
            }

        # 1. Verify Checksums
        checksums_path = mm_dir / "checksums.json"
        if checksums_path.exists():
            try:
                with open(checksums_path, "r", encoding="utf-8") as f:
                    stored_checksums = json.load(f)
                for fname, expected_hash in stored_checksums.items():
                    fpath = mm_dir / fname if fname != "multimodal_index.json" else mm_dir / "indexes" / fname
                    if not fpath.exists():
                        errors.append(f"Missing referenced file from checksums: {fname}")
                        continue
                    h = hashlib.sha256()
                    with open(fpath, "rb") as f:
                        while chunk := f.read(65536):
                            h.update(chunk)
                    actual_hash = h.hexdigest()
                    if actual_hash != expected_hash:
                        errors.append(
                            f"Checksum mismatch for {fname}: expected {expected_hash}, got {actual_hash}"
                        )
            except Exception as e:
                errors.append(f"Failed to verify checksums: {e}")
        else:
            warnings.append("No checksums.json found in multimodal directory.")

        # 2. Manifest Validation
        manifest = storage.read_manifest()
        if not manifest:
            errors.append("Missing or unparseable manifest.json")
        else:
            if manifest.schema_version != "1.0.0":
                errors.append(f"Unsupported schema version: {manifest.schema_version}")

        # 3. Observations Validation & Boundary Enforcement
        observations = storage.read_observations()
        if not observations:
            warnings.append("No observations present in observations.jsonl")

        for idx, obs in enumerate(observations, 1):
            # Check timestamps
            if obs.timestamp_ns <= 0:
                errors.append(f"Observation #{idx} ({obs.observation_id}) has invalid timestamp_ns <= 0")
            if obs.relative_time_ms < 0:
                errors.append(f"Observation #{idx} ({obs.observation_id}) has relative_time_ms < 0")
            if obs.duration_ms < 0:
                errors.append(f"Observation #{idx} ({obs.observation_id}) has negative duration_ms")

            # Check confidence bounds
            if not (0.0 <= obs.confidence <= 1.0):
                errors.append(f"Observation #{idx} ({obs.observation_id}) confidence out of [0, 1] range: {obs.confidence}")

            # Check grounding & provenance
            if obs.grounded and not obs.evidence_refs:
                errors.append(
                    f"Observation #{idx} ({obs.observation_id}) marked grounded=True but has empty evidence_refs"
                )

            # CRITICAL: Strict Semantic Boundary Check
            if _BOUNDARY_REGEX.search(obs.description):
                errors.append(
                    f"SEMANTIC BOUNDARY VIOLATION in observation '{obs.observation_id}': "
                    f"Description contains forbidden Phase 7+ intent/goal phrasing: '{obs.description}'"
                )

        return {
            "valid": len(errors) == 0,
            "session_id": session_id,
            "total_observations": len(observations),
            "errors": errors,
            "warnings": warnings,
        }
