"""Integrity, schema, security, and semantic boundary validator for Phase 7 intent artifacts."""

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Optional

from teach_a_skill.intent.models import (
    ActionType,
    DemonstrationUnderstanding,
    IntentManifest,
    IntentType,
)
from teach_a_skill.intent.storage import IntentStorage

# Forbidden execution patterns that must never exist in semantic understanding output
FORBIDDEN_EXECUTION_PATTERNS = [
    r"\bexec\s*\(",
    r"\beval\s*\(",
    r"\bsubprocess\b",
    r"\bpyautogui\b",
    r"\bapplescript\b",
    r"\bosascript\b",
    r"\bclick\s*\(\s*\d+\s*,\s*\d+\s*\)",
    r"\btype\s*\(",
    r"\bmove_to\s*\(",
    r"\bpress_key\s*\(",
    r"\bbash\s+-c\b",
    r"\bos\.system\b",
    r"\bcompile_skill\b",
    r"\bexecute_skill\b",
]

MAX_ALLOWED_STAGES = 500
MAX_ALLOWED_ACTIONS = 2000
MAX_ALLOWED_ENTITIES = 1000
MAX_TEXT_LENGTH = 10000


class IntentValidator:
    """Validates structural integrity, confidence bounds, evidence lineage, and semantic boundaries."""

    def __init__(self) -> None:
        self._compiled_forbidden = [
            re.compile(p, re.IGNORECASE) for p in FORBIDDEN_EXECUTION_PATTERNS
        ]

    def validate_understanding(self, u: DemonstrationUnderstanding) -> list[str]:
        """Perform comprehensive semantic and boundary validation on DemonstrationUnderstanding."""
        errors: list[str] = []

        # 1. Basic identifiers
        if not u.task_id or not isinstance(u.task_id, str):
            errors.append("Invalid or missing task_id")
        if not u.session_id or not isinstance(u.session_id, str):
            errors.append("Invalid or missing session_id")
        if not u.task_name or not isinstance(u.task_name, str):
            errors.append("Invalid or missing task_name")
        if not u.goal or not isinstance(u.goal, str):
            errors.append("Invalid or missing goal")

        # 2. Confidence bounds
        if not (0.0 <= u.confidence <= 1.0):
            errors.append(f"Confidence {u.confidence} out of valid range [0.0, 1.0]")

        # 3. Resource & cardinality limits
        if len(u.stages) > MAX_ALLOWED_STAGES:
            errors.append(f"Stage count {len(u.stages)} exceeds limit {MAX_ALLOWED_STAGES}")
        if len(u.actions) > MAX_ALLOWED_ACTIONS:
            errors.append(f"Action count {len(u.actions)} exceeds limit {MAX_ALLOWED_ACTIONS}")
        if len(u.entities) > MAX_ALLOWED_ENTITIES:
            errors.append(f"Entity count {len(u.entities)} exceeds limit {MAX_ALLOWED_ENTITIES}")

        # 4. Text bounds
        if len(u.description) > MAX_TEXT_LENGTH:
            errors.append(f"Description length {len(u.description)} exceeds limit {MAX_TEXT_LENGTH}")

        # 5. Semantic boundary check: Reject any execution scripts / automation code
        all_text_content = [
            u.task_name,
            u.description,
            u.goal,
        ]
        for s in u.stages:
            all_text_content.extend([s.name, s.description])
        for a in u.actions:
            all_text_content.extend([a.description] + a.state_effects)
        for e in u.entities:
            all_text_content.extend([e.label, e.entity_type])

        for text in all_text_content:
            for pattern in self._compiled_forbidden:
                if pattern.search(text):
                    errors.append(
                        f"Semantic boundary violation: Forbidden execution pattern detected in text: '{text[:80]}'"
                    )
                    break

        # 6. Stage validation
        stage_ids = set()
        for idx, stage in enumerate(u.stages):
            if not stage.stage_id:
                errors.append(f"Stage at index {idx} missing stage_id")
            elif stage.stage_id in stage_ids:
                errors.append(f"Duplicate stage_id '{stage.stage_id}'")
            stage_ids.add(stage.stage_id)

            if not (0.0 <= stage.confidence <= 1.0):
                errors.append(f"Stage {stage.stage_id} confidence {stage.confidence} out of range [0.0, 1.0]")
            if stage.start_time_ms < 0 or stage.end_time_ms < 0:
                errors.append(f"Stage {stage.stage_id} has negative timestamp")
            if stage.start_time_ms > stage.end_time_ms:
                errors.append(
                    f"Stage {stage.stage_id} start_time_ms ({stage.start_time_ms}) > end_time_ms ({stage.end_time_ms})"
                )

        # 7. Action validation
        action_ids = set()
        for idx, act in enumerate(u.actions):
            if not act.action_id:
                errors.append(f"Action at index {idx} missing action_id")
            elif act.action_id in action_ids:
                errors.append(f"Duplicate action_id '{act.action_id}'")
            action_ids.add(act.action_id)

            if not (0.0 <= act.confidence <= 1.0):
                errors.append(f"Action {act.action_id} confidence {act.confidence} out of range [0.0, 1.0]")
            if act.timestamp_ms < 0:
                errors.append(f"Action {act.action_id} has negative timestamp {act.timestamp_ms}")
            if not isinstance(act.action_type, ActionType):
                try:
                    ActionType(act.action_type)
                except ValueError:
                    errors.append(f"Action {act.action_id} has invalid action_type '{act.action_type}'")

        # 8. Primary intent validation
        if u.primary_intent:
            pi = u.primary_intent
            if not (0.0 <= pi.confidence <= 1.0):
                errors.append(f"Primary intent confidence {pi.confidence} out of range [0.0, 1.0]")
            if not isinstance(pi.intent_type, IntentType):
                try:
                    IntentType(pi.intent_type)
                except ValueError:
                    errors.append(f"Primary intent has invalid intent_type '{pi.intent_type}'")

        return errors

    def validate_manifest(self, manifest: IntentManifest) -> list[str]:
        """Validate intent manifest fields."""
        errors: list[str] = []
        if not manifest.manifest_id:
            errors.append("Missing manifest_id")
        if not manifest.session_id:
            errors.append("Missing session_id")
        if not (0.0 <= manifest.overall_confidence <= 1.0):
            errors.append(f"Overall confidence {manifest.overall_confidence} out of range [0.0, 1.0]")
        return errors

    def validate_storage_integrity(self, storage: IntentStorage) -> list[str]:
        """Verify checksums and completeness of files stored in intent partition."""
        errors: list[str] = []
        if not storage.exists():
            return ["Intent partition does not exist"]

        checksums = storage.read_checksums()
        if not checksums:
            errors.append("Missing or unreadable checksums.json in intent partition")
            return errors

        for rel_path, expected_hash in checksums.items():
            file_path = storage.intent_dir / rel_path
            if not file_path.exists():
                errors.append(f"Missing file recorded in checksums: {rel_path}")
                continue
            with open(file_path, "rb") as f:
                actual_hash = hashlib.sha256(f.read()).hexdigest()
            if actual_hash != expected_hash:
                errors.append(
                    f"Checksum mismatch for {rel_path}: expected {expected_hash}, got {actual_hash}"
                )

        return errors
