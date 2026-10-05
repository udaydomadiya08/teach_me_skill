"""Integrity, security, and schema validator for persistent Skill Memory.

Enforces bounds, fingerprint determinism, checksum correctness, path safety,
and non-execution boundary guards.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

from teach_a_skill.memory.models import SEMVER_REGEX, SkillRecord, SkillVersionRecord
from teach_a_skill.memory.storage import SkillMemoryStorage
from teach_a_skill.skill.validator import SkillValidator

logger = logging.getLogger(__name__)


class SkillMemoryValidator:
    """Validates persistent skill memory structures, integrity, and security."""

    def __init__(self, storage: SkillMemoryStorage) -> None:
        self.storage = storage
        self.ir_validator = SkillValidator()

    def validate_skill_record(self, record: SkillRecord) -> list[str]:
        """Validate top-level SkillRecord structure and metadata."""
        errors: list[str] = []

        if not record.skill_id:
            errors.append("SkillRecord missing skill_id.")
        elif not re.match(r"^[a-zA-Z0-9_\-]+$", record.skill_id):
            errors.append(f"Invalid characters in skill_id '{record.skill_id}'.")

        if not record.canonical_name:
            errors.append("SkillRecord missing canonical_name.")

        if record.current_version:
            if not SEMVER_REGEX.match(record.current_version):
                errors.append(
                    f"current_version '{record.current_version}' is not valid semantic version."
                )
            if record.current_version not in record.versions:
                errors.append(
                    f"current_version '{record.current_version}' not found in registered versions list."
                )

        for v in record.versions:
            if not SEMVER_REGEX.match(v):
                errors.append(f"Registered version '{v}' is not a valid semantic version.")

        return errors

    def validate_version_record(
        self, record: SkillVersionRecord, check_ir: bool = True
    ) -> list[str]:
        """Validate SkillVersionRecord schema, hashes, and IR."""
        errors: list[str] = []

        if not record.skill_id:
            errors.append("SkillVersionRecord missing skill_id.")
        if not SEMVER_REGEX.match(record.version):
            errors.append(f"Version '{record.version}' is not a valid semantic version.")

        if check_ir and record.skill_ir:
            # Delegate to Phase 8 validator for IR validation and execution payload blocking
            ir_errors = self.ir_validator.validate(record.skill_ir)
            errors.extend(ir_errors)

            expected_fp = record.skill_ir.compute_canonical_fingerprint()
            if record.fingerprint and record.fingerprint != expected_fp:
                errors.append(
                    f"Version fingerprint mismatch: recorded '{record.fingerprint}' != computed '{expected_fp}'."
                )

        return errors

    def validate_storage_integrity(self, skill_id: str) -> list[str]:
        """Verify on-disk hashes and files for a skill and all its versions."""
        errors: list[str] = []
        skill_dir = self.storage.get_skill_dir(skill_id)
        if not skill_dir.is_dir():
            return [f"Skill directory does not exist: {skill_dir}"]

        rec = self.storage.load_skill_record(skill_id)
        if not rec:
            return [f"Corrupted or missing manifest.json in {skill_dir}"]

        errors.extend(self.validate_skill_record(rec))

        # Check each version
        versions = self.storage.list_versions(skill_id)
        for v in versions:
            vdir = self.storage.get_version_dir(skill_id, v)
            skill_json = vdir / "skill.json"
            checksum_json = vdir / "checksum.json"
            vm_json = vdir / "version_manifest.json"

            if not skill_json.is_file():
                errors.append(f"Missing skill.json in version {v} of {skill_id}.")
                continue
            if not checksum_json.is_file():
                errors.append(f"Missing checksum.json in version {v} of {skill_id}.")
                continue
            if not vm_json.is_file():
                errors.append(f"Missing version_manifest.json in version {v} of {skill_id}.")
                continue

            # Verify checksum
            try:
                skill_bytes = skill_json.read_bytes()
                computed_sha = hashlib.sha256(skill_bytes).hexdigest()
                with open(checksum_json, "r", encoding="utf-8") as f:
                    cdata = json.load(f)
                expected_sha = cdata.get("skill.json")
                if computed_sha != expected_sha:
                    errors.append(
                        f"Checksum mismatch in {skill_id} v{v}: recorded {expected_sha} != actual {computed_sha}."
                    )
            except Exception as e:
                errors.append(f"Failed to verify checksum in {skill_id} v{v}: {e}")

            vrec = self.storage.load_version(skill_id, v, load_ir=True)
            if vrec:
                errors.extend(self.validate_version_record(vrec, check_ir=True))

        return errors
