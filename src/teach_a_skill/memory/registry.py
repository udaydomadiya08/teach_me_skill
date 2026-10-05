"""Central Skill Registry for persistent Skill Memory, versioning, and lineage.

Provides atomic, thread-safe, and process-safe registry operations without any execution capabilities.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from teach_a_skill.core.errors import StorageError
from teach_a_skill.interfaces.storage import IStorageManager
from teach_a_skill.memory.cache import SkillMemoryCache
from teach_a_skill.memory.comparator import SkillComparator
from teach_a_skill.memory.matching import SkillMatcher
from teach_a_skill.memory.models import (
    ConflictMatch,
    DemonstrationLineageRecord,
    DuplicateMatch,
    RelationshipType,
    RollbackRecord,
    SearchResult,
    SkillRecord,
    SkillRelationshipRecord,
    SkillStatus,
    SkillVersionRecord,
    VariantMatch,
    VersionBump,
    VersionDiff,
    format_semver,
    parse_semver,
)
from teach_a_skill.memory.search import SkillSearchEngine
from teach_a_skill.memory.storage import SkillMemoryStorage
from teach_a_skill.memory.validator import SkillMemoryValidator
from teach_a_skill.skill.models import SkillIR

logger = logging.getLogger(__name__)


class SkillRegistry:
    """Persistent, versioned registry for reusable AI skills."""

    def __init__(self, storage_manager: IStorageManager) -> None:
        self.storage_manager = storage_manager
        self.storage = SkillMemoryStorage(storage_manager)
        self.validator = SkillMemoryValidator(self.storage)
        self.cache = SkillMemoryCache(storage_manager)
        self.search_engine = SkillSearchEngine(self.storage)

    # -------------------------------------------------------------------------
    # Skill Registration and Version Publishing
    # -------------------------------------------------------------------------

    def register_skill(
        self,
        skill_ir: SkillIR,
        initial_version: str = "1.0.0",
        status: SkillStatus = SkillStatus.PUBLISHED,
        source_demo_id: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> tuple[SkillRecord, SkillVersionRecord]:
        """Register a new Skill IR into persistent memory as initial version."""
        parse_semver(initial_version)

        # Skill ID determinism: use skill_id from IR or derive from fingerprint
        skill_id = skill_ir.skill_id
        if not skill_id or skill_id == "skill_default":
            fp = skill_ir.compute_canonical_fingerprint()
            skill_id = f"skill_{fp[:16]}"
            skill_ir.skill_id = skill_id

        with self.storage.acquire_lock():
            if self.storage.skill_exists(skill_id):
                # Skill already exists, check if initial_version exists
                if self.storage.version_exists(skill_id, initial_version):
                    logger.info(
                        f"Skill '{skill_id}' v{initial_version} already registered. Returning existing."
                    )
                    s_rec = self.storage.load_skill_record(skill_id)
                    v_rec = self.storage.load_version(skill_id, initial_version)
                    if s_rec and v_rec:
                        return s_rec, v_rec

            # Create or update SkillRecord
            now = datetime.now(timezone.utc).isoformat()
            demo_ids = list(skill_ir.provenance.get("source_demonstration_ids", []))
            if source_demo_id and source_demo_id not in demo_ids:
                demo_ids.append(source_demo_id)

            dependencies = [d.name for d in skill_ir.dependencies]

            skill_rec = SkillRecord(
                skill_id=skill_id,
                canonical_name=skill_ir.name,
                description=skill_ir.description,
                status=status,
                current_version=initial_version,
                versions=[initial_version],
                source_demonstrations=demo_ids,
                tags=tags or ["productivity", "desktop"],
                capabilities=[s.action_type.value for s in skill_ir.steps],
                dependencies=dependencies,
                created_at=now,
                updated_at=now,
                schema_version="1.0.0",
                fingerprint=skill_ir.compute_canonical_fingerprint(),
                provenance=dict(skill_ir.provenance),
            )

            # Create SkillVersionRecord
            version_rec = SkillVersionRecord(
                skill_id=skill_id,
                version=initial_version,
                status=status,
                fingerprint=skill_ir.compute_canonical_fingerprint(),
                checksum="",  # Populated during atomic save
                created_at=now,
                parent_version=None,
                source_demonstrations=demo_ids,
                skill_ir=skill_ir,
                metadata={"registered_by": "teach-skill"},
                schema_version="1.0.0",
            )

            # Validate before saving
            val_errors = self.validator.validate_version_record(version_rec)
            if val_errors:
                raise StorageError(
                    f"Validation failed for skill version '{skill_id}@{initial_version}': {val_errors}"
                )

            # Persist version first
            self.storage.save_version(version_rec)
            self.storage.save_skill_record(skill_rec)

            # Record demonstration lineage
            for d_id in demo_ids:
                lin_rec = DemonstrationLineageRecord(
                    demonstration_id=d_id,
                    skill_id=skill_id,
                    skill_version=initial_version,
                    relationship_type=RelationshipType.DERIVED_FROM,
                    evidence_refs=list(skill_ir.evidence_refs),
                    confidence=skill_ir.confidence,
                )
                self.storage.append_demonstration_lineage(lin_rec)

            self.rebuild_indexes()
            return skill_rec, version_rec

    def publish_version(
        self,
        skill_id: str,
        skill_ir: SkillIR,
        bump_type: Optional[VersionBump] = None,
        explicit_version: Optional[str] = None,
        source_demo_id: Optional[str] = None,
        parent_version: Optional[str] = None,
        status: SkillStatus = SkillStatus.PUBLISHED,
    ) -> SkillVersionRecord:
        """Publish a new immutable version of an existing skill."""
        with self.storage.acquire_lock():
            skill_rec = self.storage.load_skill_record(skill_id)
            if not skill_rec:
                raise StorageError(f"Skill '{skill_id}' does not exist in registry.")

            parent_v = parent_version or skill_rec.current_version or skill_rec.versions[-1]
            parent_rec = self.storage.load_version(skill_id, parent_v, load_ir=True)
            if not parent_rec or not parent_rec.skill_ir:
                raise StorageError(f"Parent version '{parent_v}' not found for skill '{skill_id}'.")

            # Compare against parent to classify bump
            diff = SkillComparator.compare(
                skill_id=skill_id,
                version_a_str=parent_v,
                ir_a=parent_rec.skill_ir,
                version_b_str="new",
                ir_b=skill_ir,
            )

            if diff.recommended_bump == VersionBump.CONFLICT:
                logger.warning(f"Semantic conflict detected: {diff.explanation}")

            effective_bump = bump_type or diff.recommended_bump
            if effective_bump == VersionBump.CONFLICT:
                effective_bump = VersionBump.MAJOR

            # Determine new semver
            if explicit_version:
                parse_semver(explicit_version)
                new_version = explicit_version
            else:
                maj, min_, pat = parse_semver(parent_v)
                if effective_bump == VersionBump.MAJOR:
                    new_version = format_semver(maj + 1, 0, 0)
                elif effective_bump == VersionBump.MINOR:
                    new_version = format_semver(maj, min_ + 1, 0)
                else:
                    new_version = format_semver(maj, min_, pat + 1)

            if self.storage.version_exists(skill_id, new_version):
                raise StorageError(
                    f"Version '{new_version}' already exists for skill '{skill_id}'."
                )

            now = datetime.now(timezone.utc).isoformat()
            demo_ids = list(skill_ir.provenance.get("source_demonstration_ids", []))
            if source_demo_id and source_demo_id not in demo_ids:
                demo_ids.append(source_demo_id)

            new_v_rec = SkillVersionRecord(
                skill_id=skill_id,
                version=new_version,
                status=status,
                fingerprint=skill_ir.compute_canonical_fingerprint(),
                checksum="",
                created_at=now,
                parent_version=parent_v,
                supersedes=parent_v,
                source_demonstrations=demo_ids,
                skill_ir=skill_ir,
                metadata={
                    "bump_type": effective_bump.value,
                    "explanation": diff.explanation,
                },
            )

            # Validate new version
            val_errors = self.validator.validate_version_record(new_v_rec)
            if val_errors:
                raise StorageError(
                    f"Validation failed for new version '{skill_id}@{new_version}': {val_errors}"
                )

            # Persist version
            self.storage.save_version(new_v_rec)

            # Update parent record supersession
            parent_rec.superseded_by = new_version
            if parent_rec.status == SkillStatus.PUBLISHED:
                parent_rec.status = SkillStatus.SUPERSEDED

            # Update skill manifest
            if new_version not in skill_rec.versions:
                skill_rec.versions.append(new_version)
            skill_rec.current_version = new_version
            skill_rec.updated_at = now
            for d in demo_ids:
                if d not in skill_rec.source_demonstrations:
                    skill_rec.source_demonstrations.append(d)
            self.storage.save_skill_record(skill_rec)

            # Lineage & Relationship records
            for d in demo_ids:
                lin = DemonstrationLineageRecord(
                    demonstration_id=d,
                    skill_id=skill_id,
                    skill_version=new_version,
                    relationship_type=RelationshipType.REVISION_OF,
                    evidence_refs=list(skill_ir.evidence_refs),
                    confidence=skill_ir.confidence,
                )
                self.storage.append_demonstration_lineage(lin)

            rel = SkillRelationshipRecord(
                source_skill_id=skill_id,
                source_version=new_version,
                target_skill_id=skill_id,
                target_version=parent_v,
                relationship_type=RelationshipType.SUPERSEDES,
                reason=diff.explanation,
                confidence=1.0,
            )
            self.storage.append_relationship(rel)

            # Cache diff
            self.cache.put_diff(parent_rec.fingerprint, new_v_rec.fingerprint, diff)

            self.rebuild_indexes()
            return new_v_rec

    # -------------------------------------------------------------------------
    # Retrieval and Inspection
    # -------------------------------------------------------------------------

    def get_skill(self, skill_id: str) -> Optional[SkillRecord]:
        """Retrieve top-level skill record."""
        return self.storage.load_skill_record(skill_id)

    def get_version(
        self, skill_id: str, version: str, load_ir: bool = True
    ) -> Optional[SkillVersionRecord]:
        """Retrieve a specific immutable skill version."""
        return self.storage.load_version(skill_id, version, load_ir=load_ir)

    def list_skills(
        self, status: Optional[SkillStatus] = None, tag: Optional[str] = None
    ) -> list[SkillRecord]:
        """List all registered skills with optional status and tag filters."""
        res: list[SkillRecord] = []
        for sid in self.storage.list_skill_ids():
            rec = self.storage.load_skill_record(sid)
            if not rec:
                continue
            if status and rec.status != status:
                continue
            if tag and tag.lower() not in [t.lower() for t in rec.tags]:
                continue
            res.append(rec)
        return sorted(res, key=lambda r: r.skill_id)

    def list_versions(self, skill_id: str) -> list[str]:
        """List all version strings for a skill."""
        return self.storage.list_versions(skill_id)

    # -------------------------------------------------------------------------
    # Lifecycle: Set Current, Rollback, Archive, Restore
    # -------------------------------------------------------------------------

    def set_current_version(
        self,
        skill_id: str,
        version: str,
        reason: Optional[str] = None,
        operator: str = "user",
    ) -> SkillRecord:
        """Explicitly change the active current version of a skill."""
        with self.storage.acquire_lock():
            rec = self.storage.load_skill_record(skill_id)
            if not rec:
                raise StorageError(f"Skill '{skill_id}' not found.")
            if version not in rec.versions or not self.storage.version_exists(skill_id, version):
                raise StorageError(f"Version '{version}' does not exist for skill '{skill_id}'.")

            prev_version = rec.current_version or ""
            rec.current_version = version
            rec.updated_at = datetime.now(timezone.utc).isoformat()
            self.storage.save_skill_record(rec)

            if prev_version and prev_version != version:
                rb = RollbackRecord(
                    skill_id=skill_id,
                    previous_current_version=prev_version,
                    rollback_target=version,
                    rollback_reason=reason or f"Switched current version to {version}",
                    operator=operator,
                )
                self.storage.append_rollback(rb)

            self.rebuild_indexes()
            return rec

    def rollback_current_version(
        self,
        skill_id: str,
        target_version: str,
        reason: Optional[str] = None,
        operator: str = "user",
    ) -> SkillRecord:
        """Rollback active version to an earlier historical version with audit log."""
        return self.set_current_version(
            skill_id=skill_id,
            version=target_version,
            reason=reason or f"Rollback to {target_version}",
            operator=operator,
        )

    def archive_skill(
        self, skill_id: str, version: Optional[str] = None
    ) -> SkillRecord:
        """Archive a skill or a specific version without destroying history."""
        with self.storage.acquire_lock():
            rec = self.storage.load_skill_record(skill_id)
            if not rec:
                raise StorageError(f"Skill '{skill_id}' not found.")

            if version:
                v_rec = self.storage.load_version(skill_id, version, load_ir=False)
                if not v_rec:
                    raise StorageError(f"Version '{version}' not found for skill '{skill_id}'.")
                v_rec.status = SkillStatus.ARCHIVED
                # Update manifest
                vdir = self.storage.get_version_dir(skill_id, version)
                vm_path = vdir / "version_manifest.json"
                import json
                with open(vm_path, "w", encoding="utf-8") as f:
                    json.dump(v_rec.to_dict(include_ir=False), f, indent=2, sort_keys=True)
            else:
                rec.status = SkillStatus.ARCHIVED
                rec.updated_at = datetime.now(timezone.utc).isoformat()
                self.storage.save_skill_record(rec)

            self.rebuild_indexes()
            return rec

    def restore_skill(
        self, skill_id: str, version: Optional[str] = None
    ) -> SkillRecord:
        """Restore an archived skill or version back to VALIDATED/PUBLISHED."""
        with self.storage.acquire_lock():
            rec = self.storage.load_skill_record(skill_id)
            if not rec:
                raise StorageError(f"Skill '{skill_id}' not found.")

            # Validate integrity before restoring
            errors = self.validator.validate_storage_integrity(skill_id)
            if errors:
                raise StorageError(f"Cannot restore corrupted skill '{skill_id}': {errors}")

            if version:
                v_rec = self.storage.load_version(skill_id, version, load_ir=False)
                if not v_rec:
                    raise StorageError(f"Version '{version}' not found for skill '{skill_id}'.")
                v_rec.status = SkillStatus.PUBLISHED
                vdir = self.storage.get_version_dir(skill_id, version)
                vm_path = vdir / "version_manifest.json"
                import json
                with open(vm_path, "w", encoding="utf-8") as f:
                    json.dump(v_rec.to_dict(include_ir=False), f, indent=2, sort_keys=True)
            else:
                rec.status = SkillStatus.PUBLISHED
                rec.updated_at = datetime.now(timezone.utc).isoformat()
                self.storage.save_skill_record(rec)

            self.rebuild_indexes()
            return rec

    # -------------------------------------------------------------------------
    # Comparison, Matching, Duplicates, and Conflicts
    # -------------------------------------------------------------------------

    def compare_versions(
        self, skill_id: str, version_a: str, version_b: str
    ) -> VersionDiff:
        """Compare two versions of a skill."""
        rec_a = self.get_version(skill_id, version_a, load_ir=True)
        rec_b = self.get_version(skill_id, version_b, load_ir=True)

        if not rec_a or not rec_a.skill_ir:
            raise StorageError(f"Version '{version_a}' not found for skill '{skill_id}'.")
        if not rec_b or not rec_b.skill_ir:
            raise StorageError(f"Version '{version_b}' not found for skill '{skill_id}'.")

        # Check cache
        cached = self.cache.get_diff(rec_a.fingerprint, rec_b.fingerprint)
        if cached:
            # Reconstruct VersionDiff from cached dict
            return VersionDiff(
                skill_id=cached["skill_id"],
                version_a=cached["version_a"],
                version_b=cached["version_b"],
                recommended_bump=VersionBump(cached["recommended_bump"]),
                explanation=cached["explanation"],
                semantic_changes=cached.get("semantic_changes", []),
                parameter_changes=cached.get("parameter_changes", []),
                step_changes=cached.get("step_changes", []),
                precondition_changes=cached.get("precondition_changes", []),
                postcondition_changes=cached.get("postcondition_changes", []),
                grounding_changes=cached.get("grounding_changes", []),
                dependency_changes=cached.get("dependency_changes", []),
                confidence_delta=cached.get("confidence_delta", 0.0),
                provenance_differences=cached.get("provenance_differences", []),
            )

        diff = SkillComparator.compare(
            skill_id=skill_id,
            version_a_str=version_a,
            ir_a=rec_a.skill_ir,
            version_b_str=version_b,
            ir_b=rec_b.skill_ir,
        )
        self.cache.put_diff(rec_a.fingerprint, rec_b.fingerprint, diff)
        return diff

    def detect_duplicates(self, threshold: float = 0.85) -> list[DuplicateMatch]:
        """Detect candidate duplicates across all skills and active versions."""
        skills = self.list_skills()
        matches: list[DuplicateMatch] = []

        active_versions: list[tuple[str, str, SkillIR]] = []
        for s in skills:
            if s.current_version:
                vrec = self.get_version(s.skill_id, s.current_version, load_ir=True)
                if vrec and vrec.skill_ir:
                    active_versions.append((s.skill_id, s.current_version, vrec.skill_ir))

        for i in range(len(active_versions)):
            for j in range(i + 1, len(active_versions)):
                sid_a, ver_a, ir_a = active_versions[i]
                sid_b, ver_b, ir_b = active_versions[j]
                dup = SkillMatcher.detect_duplicate(
                    skill_id_a=sid_a,
                    version_a=ver_a,
                    ir_a=ir_a,
                    skill_id_b=sid_b,
                    version_b=ver_b,
                    ir_b=ir_b,
                    threshold=threshold,
                )
                if dup:
                    matches.append(dup)

        return matches

    def detect_variants(self, skill_id: str) -> list[VariantMatch]:
        """Detect alternate action pathways across versions of a specific skill."""
        versions = self.storage.list_versions(skill_id)
        matches: list[VariantMatch] = []
        loaded: list[tuple[str, SkillIR]] = []
        for v in versions:
            vrec = self.get_version(skill_id, v, load_ir=True)
            if vrec and vrec.skill_ir:
                loaded.append((v, vrec.skill_ir))

        for i in range(len(loaded)):
            for j in range(i + 1, len(loaded)):
                v_a, ir_a = loaded[i]
                v_b, ir_b = loaded[j]
                var = SkillMatcher.detect_variant(skill_id, v_a, ir_a, v_b, ir_b)
                if var:
                    matches.append(var)
        return matches

    def detect_conflicts(self, skill_id: str) -> list[ConflictMatch]:
        """Detect semantic conflicts across versions of a skill."""
        versions = self.storage.list_versions(skill_id)
        matches: list[ConflictMatch] = []
        loaded: list[tuple[str, SkillIR]] = []
        for v in versions:
            vrec = self.get_version(skill_id, v, load_ir=True)
            if vrec and vrec.skill_ir:
                loaded.append((v, vrec.skill_ir))

        for i in range(len(loaded)):
            for j in range(i + 1, len(loaded)):
                v_a, ir_a = loaded[i]
                v_b, ir_b = loaded[j]
                conf = SkillMatcher.detect_conflict(skill_id, v_a, ir_a, v_b, ir_b)
                if conf:
                    matches.append(conf)
        return matches

    # -------------------------------------------------------------------------
    # Search and Indexing
    # -------------------------------------------------------------------------

    def search(
        self,
        query: str,
        status: Optional[SkillStatus] = None,
        tag: Optional[str] = None,
        limit: int = 50,
    ) -> list[SearchResult]:
        """Multi-dimensional search across stored skills."""
        return self.search_engine.search(
            query=query, status_filter=status, tag_filter=tag, limit=limit
        )

    def rebuild_indexes(self) -> dict[str, Any]:
        """Deterministically rebuild memory indexes from on-disk version manifests."""
        index: dict[str, Any] = {
            "version": "1.0.0",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "skills": {},
            "fingerprints": {},
            "demonstrations": {},
        }

        for sid in self.storage.list_skill_ids():
            srec = self.storage.load_skill_record(sid)
            if not srec:
                continue

            versions = self.storage.list_versions(sid)
            index["skills"][sid] = {
                "name": srec.canonical_name,
                "current_version": srec.current_version,
                "status": srec.status.value,
                "versions": versions,
                "tags": srec.tags,
            }

            for v in versions:
                vrec = self.storage.load_version(sid, v, load_ir=False)
                if vrec:
                    if vrec.fingerprint:
                        index["fingerprints"][vrec.fingerprint] = f"{sid}@{v}"
                    for d in vrec.source_demonstrations:
                        if d not in index["demonstrations"]:
                            index["demonstrations"][d] = []
                        index["demonstrations"][d].append(f"{sid}@{v}")

        self.storage.save_registry_index(index)
        return index

    def validate_memory(self) -> dict[str, list[str]]:
        """Run complete integrity validation across all skills in registry."""
        results: dict[str, list[str]] = {}
        for sid in self.storage.list_skill_ids():
            errs = self.validator.validate_storage_integrity(sid)
            if errs:
                results[sid] = errs
        return results
