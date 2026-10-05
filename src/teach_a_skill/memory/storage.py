"""Atomic, content-addressed storage manager for persistent Skill Memory.

Enforces sandboxing, staging, atomic promotions, checksums, and concurrency locks.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Generator, Optional

from teach_a_skill.core.errors import StorageError
from teach_a_skill.interfaces.storage import IStorageManager
from teach_a_skill.memory.models import (
    DemonstrationLineageRecord,
    RollbackRecord,
    SkillRecord,
    SkillRelationshipRecord,
    SkillVersionRecord,
)
from teach_a_skill.skill.models import SkillIR

logger = logging.getLogger(__name__)


class SkillMemoryStorage:
    """Manages the persistent skills/ partition, version directories, and staging."""

    def __init__(self, storage_manager: IStorageManager) -> None:
        self.storage_manager = storage_manager
        self.root_dir = storage_manager.get_path("skills")
        self.staging_dir = self.root_dir / ".skill_memory_staging"
        self.lock_file = self.root_dir / ".lock"
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.staging_dir.mkdir(parents=True, exist_ok=True)

    @contextlib.contextmanager
    def acquire_lock(self, timeout_sec: float = 5.0) -> Generator[None, None, None]:
        """Context manager providing an exclusive file lock for memory mutations."""
        self._ensure_dirs()
        lock_fd = None
        try:
            lock_fd = open(self.lock_file, "w")
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            if lock_fd is not None:
                try:
                    fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
                    lock_fd.close()
                except Exception:
                    pass

    def get_skill_dir(self, skill_id: str) -> Path:
        """Get sandboxed path to a specific skill directory."""
        if not skill_id or ".." in skill_id or "/" in skill_id or "\\" in skill_id:
            raise StorageError(f"Invalid or unsafe skill_id: '{skill_id}'")
        p = self.root_dir / skill_id
        return p

    def get_version_dir(self, skill_id: str, version: str) -> Path:
        """Get sandboxed path to a specific version directory of a skill."""
        if not version or ".." in version or "/" in version or "\\" in version:
            raise StorageError(f"Invalid or unsafe version string: '{version}'")
        return self.get_skill_dir(skill_id) / "versions" / version

    def skill_exists(self, skill_id: str) -> bool:
        """Check if skill record exists."""
        manifest_path = self.get_skill_dir(skill_id) / "manifest.json"
        return manifest_path.is_file()

    def version_exists(self, skill_id: str, version: str) -> bool:
        """Check if a specific version of a skill exists."""
        skill_json = self.get_version_dir(skill_id, version) / "skill.json"
        return skill_json.is_file()

    # -------------------------------------------------------------------------
    # Skill Record CRUD
    # -------------------------------------------------------------------------

    def save_skill_record(self, record: SkillRecord) -> None:
        """Save top-level skill manifest atomically."""
        skill_dir = self.get_skill_dir(record.skill_id)
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "versions").mkdir(exist_ok=True)
        (skill_dir / "lineage").mkdir(exist_ok=True)
        (skill_dir / "rollback").mkdir(exist_ok=True)
        (skill_dir / "indexes").mkdir(exist_ok=True)

        manifest_path = skill_dir / "manifest.json"
        tmp_path = self.staging_dir / f"manifest_{record.skill_id}_{os.getpid()}.tmp"

        payload = json.dumps(record.to_dict(), indent=2, sort_keys=True)
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())

        shutil.move(str(tmp_path), str(manifest_path))

    def load_skill_record(self, skill_id: str) -> Optional[SkillRecord]:
        """Load top-level skill manifest."""
        manifest_path = self.get_skill_dir(skill_id) / "manifest.json"
        if not manifest_path.is_file():
            return None
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return SkillRecord.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to read skill manifest for '{skill_id}': {e}")
            return None

    def list_skill_ids(self) -> list[str]:
        """List all valid skill IDs in storage."""
        res: list[str] = []
        for p in self.root_dir.iterdir():
            if p.is_dir() and not p.name.startswith("."):
                manifest = p / "manifest.json"
                if manifest.is_file():
                    res.append(p.name)
        return sorted(res)

    # -------------------------------------------------------------------------
    # Skill Version CRUD (Immutable)
    # -------------------------------------------------------------------------

    def save_version(self, version_rec: SkillVersionRecord) -> None:
        """Atomically persist an immutable skill version."""
        skill_id = version_rec.skill_id
        version = version_rec.version

        target_version_dir = self.get_version_dir(skill_id, version)
        if target_version_dir.exists():
            raise StorageError(
                f"Version '{version}' for skill '{skill_id}' already exists and is immutable."
            )

        # Stage directory
        stage_dir = self.staging_dir / f"{skill_id}_{version}_{os.getpid()}"
        if stage_dir.exists():
            shutil.rmtree(stage_dir)
        stage_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 1. Write skill.json
            if version_rec.skill_ir is None:
                raise StorageError(f"Cannot save version '{version}' without SkillIR.")

            skill_json_path = stage_dir / "skill.json"
            skill_dict = version_rec.skill_ir.to_dict()
            skill_bytes = json.dumps(skill_dict, indent=2, sort_keys=True).encode("utf-8")
            with open(skill_json_path, "wb") as f:
                f.write(skill_bytes)
                f.flush()
                os.fsync(f.fileno())

            # 2. Compute and write checksum.json
            sha256 = hashlib.sha256(skill_bytes).hexdigest()
            version_rec.checksum = sha256
            if not version_rec.fingerprint:
                version_rec.fingerprint = version_rec.compute_version_fingerprint()

            checksum_path = stage_dir / "checksum.json"
            checksum_data = {
                "skill.json": sha256,
                "fingerprint": version_rec.fingerprint,
                "version": version,
                "schema_version": version_rec.schema_version,
            }
            with open(checksum_path, "w", encoding="utf-8") as f:
                json.dump(checksum_data, f, indent=2, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())

            # 3. Write version_manifest.json
            vm_path = stage_dir / "version_manifest.json"
            with open(vm_path, "w", encoding="utf-8") as f:
                json.dump(version_rec.to_dict(include_ir=False), f, indent=2, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())

            # 4. Atomic promotion
            target_version_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(stage_dir), str(target_version_dir))
        finally:
            if stage_dir.exists():
                shutil.rmtree(stage_dir, ignore_errors=True)

    def load_version(
        self, skill_id: str, version: str, load_ir: bool = True
    ) -> Optional[SkillVersionRecord]:
        """Load an immutable skill version record and optionally its SkillIR."""
        vdir = self.get_version_dir(skill_id, version)
        if not vdir.is_dir():
            return None

        vm_path = vdir / "version_manifest.json"
        skill_json_path = vdir / "skill.json"

        if not vm_path.is_file() or not skill_json_path.is_file():
            logger.warning(f"Incomplete version directory: {vdir}")
            return None

        try:
            with open(vm_path, "r", encoding="utf-8") as f:
                vm_data = json.load(f)
            rec = SkillVersionRecord.from_dict(vm_data)

            if load_ir:
                with open(skill_json_path, "r", encoding="utf-8") as f:
                    ir_data = json.load(f)
                rec.skill_ir = SkillIR.from_dict(ir_data)
            return rec
        except Exception as e:
            logger.error(f"Error reading version '{version}' of skill '{skill_id}': {e}")
            return None

    def list_versions(self, skill_id: str) -> list[str]:
        """List all version strings for a skill, sorted according to semver."""
        vroot = self.get_skill_dir(skill_id) / "versions"
        if not vroot.is_dir():
            return []
        res = []
        for p in vroot.iterdir():
            if p.is_dir() and not p.name.startswith("."):
                if (p / "skill.json").is_file():
                    res.append(p.name)

        # Sort with semver if valid
        from teach_a_skill.memory.models import parse_semver

        def semver_key(v: str) -> tuple[int, int, int]:
            try:
                return parse_semver(v)
            except Exception:
                return (999, 999, 999)

        return sorted(res, key=semver_key)

    # -------------------------------------------------------------------------
    # Lineage and Relationships
    # -------------------------------------------------------------------------

    def append_demonstration_lineage(
        self, record: DemonstrationLineageRecord
    ) -> None:
        """Append a demonstration lineage record."""
        skill_dir = self.get_skill_dir(record.skill_id)
        lineage_file = skill_dir / "lineage" / "demonstrations.jsonl"
        lineage_file.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record.to_dict()) + "\n"
        with open(lineage_file, "a", encoding="utf-8") as f:
            f.write(line)

    def load_demonstration_lineage(
        self, skill_id: str
    ) -> list[DemonstrationLineageRecord]:
        """Load all demonstration lineage records for a skill."""
        lineage_file = self.get_skill_dir(skill_id) / "lineage" / "demonstrations.jsonl"
        if not lineage_file.is_file():
            return []
        records: list[DemonstrationLineageRecord] = []
        with open(lineage_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(
                        DemonstrationLineageRecord.from_dict(json.loads(line))
                    )
        return records

    def append_relationship(self, record: SkillRelationshipRecord) -> None:
        """Append a skill-to-skill relationship record."""
        skill_dir = self.get_skill_dir(record.source_skill_id)
        rel_file = skill_dir / "lineage" / "relationships.jsonl"
        rel_file.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record.to_dict()) + "\n"
        with open(rel_file, "a", encoding="utf-8") as f:
            f.write(line)

    def load_relationships(self, skill_id: str) -> list[SkillRelationshipRecord]:
        """Load all relationship records originating from a skill."""
        rel_file = self.get_skill_dir(skill_id) / "lineage" / "relationships.jsonl"
        if not rel_file.is_file():
            return []
        records: list[SkillRelationshipRecord] = []
        with open(rel_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(SkillRelationshipRecord.from_dict(json.loads(line)))
        return records

    # -------------------------------------------------------------------------
    # Rollback History
    # -------------------------------------------------------------------------

    def append_rollback(self, record: RollbackRecord) -> None:
        """Append an audit record for current version rollback."""
        skill_dir = self.get_skill_dir(record.skill_id)
        rb_file = skill_dir / "rollback" / "history.jsonl"
        rb_file.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record.to_dict()) + "\n"
        with open(rb_file, "a", encoding="utf-8") as f:
            f.write(line)

    def load_rollback_history(self, skill_id: str) -> list[RollbackRecord]:
        """Load rollback history for a skill."""
        rb_file = self.get_skill_dir(skill_id) / "rollback" / "history.jsonl"
        if not rb_file.is_file():
            return []
        records: list[RollbackRecord] = []
        with open(rb_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(RollbackRecord.from_dict(json.loads(line)))
        return records

    # -------------------------------------------------------------------------
    # Indexes
    # -------------------------------------------------------------------------

    def save_registry_index(self, index_data: dict[str, Any]) -> None:
        """Atomically persist the global registry index."""
        target_path = self.root_dir / "registry_index.json"
        tmp_path = self.staging_dir / f"registry_index_{os.getpid()}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(index_data, f, indent=2, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        shutil.move(str(tmp_path), str(target_path))

    def load_registry_index(self) -> Optional[dict[str, Any]]:
        """Load the global registry index."""
        target_path = self.root_dir / "registry_index.json"
        if not target_path.is_file():
            return None
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Corrupt or unreadable registry index: {e}")
            return None
