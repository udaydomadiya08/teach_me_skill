"""Strict validator and security guard for Skill IR artifacts."""

import hashlib
import json
import re
from typing import Optional

from teach_a_skill.skill.models import (
    CompilationStatus,
    SkillActionType,
    SkillIR,
    SkillManifest,
)
from teach_a_skill.skill.storage import SkillStorage

# Strict execution payload rejection patterns
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
    r"\brun_shell\b",
    r"\bexecute_shell\b",
]

MAX_ALLOWED_STEPS = 1000
MAX_ALLOWED_PARAMS = 500
MAX_ALLOWED_VARIABLES = 500


class SkillValidator:
    """Validates structural integrity, parameter consistency, fingerprinting, and execution blocking."""

    def __init__(self) -> None:
        self._compiled_forbidden = [
            re.compile(p, re.IGNORECASE) for p in FORBIDDEN_EXECUTION_PATTERNS
        ]

    def validate(self, skill: SkillIR) -> list[str]:
        """Perform comprehensive validation on SkillIR."""
        errors: list[str] = []

        # 1. Identifiers
        if not skill.skill_id or not isinstance(skill.skill_id, str):
            errors.append("Invalid or missing skill_id")
        if not skill.name or not isinstance(skill.name, str):
            errors.append("Invalid or missing skill name")
        if not skill.goal or not isinstance(skill.goal, str):
            errors.append("Invalid or missing skill goal")

        # 2. Confidence bounds
        if not (0.0 <= skill.confidence <= 1.0):
            errors.append(f"Confidence {skill.confidence} out of range [0.0, 1.0]")

        # 3. Cardinality limits
        if len(skill.steps) > MAX_ALLOWED_STEPS:
            errors.append(f"Step count {len(skill.steps)} exceeds maximum {MAX_ALLOWED_STEPS}")
        if len(skill.parameters) > MAX_ALLOWED_PARAMS:
            errors.append(f"Parameter count {len(skill.parameters)} exceeds maximum {MAX_ALLOWED_PARAMS}")
        if len(skill.variables) > MAX_ALLOWED_VARIABLES:
            errors.append(f"Variable count {len(skill.variables)} exceeds maximum {MAX_ALLOWED_VARIABLES}")

        # 4. Canonical Fingerprint Verification
        computed_fp = skill.compute_canonical_fingerprint()
        if skill.fingerprint and skill.fingerprint != computed_fp:
            errors.append(
                f"Fingerprint mismatch: declared '{skill.fingerprint}' != computed '{computed_fp}'"
            )

        # 5. Security & Executable Payload Defense
        texts_to_check: list[str] = [
            skill.name,
            skill.description,
            skill.goal,
        ]
        for p in skill.parameters:
            texts_to_check.extend([p.name, p.description, str(p.example_value or "")])
        for v in skill.variables:
            texts_to_check.extend([v.name, v.type])
        for s in skill.steps:
            texts_to_check.extend([s.target, s.description])
            for arg_k, arg_v in s.arguments.items():
                texts_to_check.extend([str(arg_k), str(arg_v)])
            if s.grounding:
                texts_to_check.extend([s.grounding.target_name, s.grounding.semantic_label])
            if s.verification:
                texts_to_check.extend([s.verification.description, s.verification.expected_state])

        for text in texts_to_check:
            for pattern in self._compiled_forbidden:
                if pattern.search(text):
                    errors.append(
                        f"Executable payload violation: Forbidden execution pattern detected in '{text[:80]}'"
                    )
                    break

        # 6. Step Integrity & Ordering
        step_ids = set()
        expected_ordinal = 1
        for idx, step in enumerate(skill.steps, 1):
            if not step.step_id:
                errors.append(f"Step at index {idx} missing step_id")
            elif step.step_id in step_ids:
                errors.append(f"Duplicate step_id '{step.step_id}'")
            step_ids.add(step.step_id)

            if step.ordinal != expected_ordinal:
                errors.append(
                    f"Step '{step.step_id}' ordinal {step.ordinal} out of sequence (expected {expected_ordinal})"
                )
            expected_ordinal += 1

            if not (0.0 <= step.confidence <= 1.0):
                errors.append(f"Step '{step.step_id}' confidence {step.confidence} out of range [0.0, 1.0]")

            if not isinstance(step.action_type, SkillActionType):
                try:
                    SkillActionType(step.action_type)
                except ValueError:
                    errors.append(f"Step '{step.step_id}' has invalid action_type '{step.action_type}'")

        # 7. Parameter Integrity
        param_ids = set()
        param_names = set()
        for p in skill.parameters:
            if not p.parameter_id:
                errors.append("Parameter missing parameter_id")
            elif p.parameter_id in param_ids:
                errors.append(f"Duplicate parameter_id '{p.parameter_id}'")
            param_ids.add(p.parameter_id)

            if p.name in param_names:
                errors.append(f"Duplicate parameter name '{p.name}'")
            param_names.add(p.name)

            if not (0.0 <= p.confidence <= 1.0):
                errors.append(f"Parameter '{p.name}' confidence {p.confidence} out of range [0.0, 1.0]")

        return errors

    def validate_manifest(self, manifest: SkillManifest) -> list[str]:
        """Validate compilation manifest."""
        errors: list[str] = []
        if not manifest.manifest_id:
            errors.append("Missing manifest_id")
        if not manifest.skill_id:
            errors.append("Missing skill_id")
        if not (0.0 <= manifest.overall_confidence <= 1.0):
            errors.append(f"Overall confidence {manifest.overall_confidence} out of range [0.0, 1.0]")
        return errors

    def validate_storage_integrity(self, storage: SkillStorage) -> list[str]:
        """Verify storage completeness and SHA-256 checksums."""
        errors: list[str] = []
        if not storage.exists():
            return ["Skill partition does not exist"]

        checksums = storage.read_checksums()
        if not checksums:
            errors.append("Missing or unreadable checksums.json in skill partition")
            return errors

        for rel_path, expected_hash in checksums.items():
            file_path = storage.skill_dir / rel_path
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
