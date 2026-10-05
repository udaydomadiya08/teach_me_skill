"""Comprehensive tests for Phase 9: Skill Format, Memory & Versioning.

Validates schemas, immutable versions, semantic versioning (PATCH/MINOR/MAJOR/CONFLICT),
lineage, comparison diffs, duplicate/variant/conflict detection, search, migrations,
real-data persistence, benchmarks, and strict non-execution boundaries.
"""

from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import pytest

from teach_a_skill.app import TeachSkillApp
from teach_a_skill.core.errors import StorageError
from teach_a_skill.memory.comparator import SkillComparator
from teach_a_skill.memory.matching import SkillMatcher
from teach_a_skill.memory.migration import SkillMigrationManager
from teach_a_skill.memory.models import (
    ConflictMatch,
    DemonstrationLineageRecord,
    DuplicateMatch,
    RelationshipType,
    RollbackRecord,
    SkillRecord,
    SkillRelationshipRecord,
    SkillStatus,
    SkillVersionRecord,
    VariantMatch,
    VersionBump,
    format_semver,
    parse_semver,
)
from teach_a_skill.memory.registry import SkillRegistry
from teach_a_skill.memory.search import SkillSearchEngine
from teach_a_skill.memory.storage import SkillMemoryStorage
from teach_a_skill.memory.validator import SkillMemoryValidator
from teach_a_skill.skill.models import (
    GroundingRequirement,
    GroundingStrategy,
    ParameterType,
    SkillActionType,
    SkillIR,
    SkillParameter,
    SkillStep,
    ValueClassification,
)
from teach_a_skill.storage.manager import StorageManager


@pytest.fixture
def temp_storage(tmp_path: Path) -> StorageManager:
    sm = StorageManager(tmp_path)
    sm.initialize_directories()
    return sm


def make_dummy_ir(
    skill_id: str = "skill_test_abc",
    name: str = "Test Save Document",
    goal: str = "Save the open document changes",
    step_count: int = 3,
) -> SkillIR:
    steps = [
        SkillStep(
            step_id=f"step_{i+1}",
            ordinal=i + 1,
            action_type=SkillActionType.ACTIVATE,
            target="Save Button" if i == 0 else f"Control_{i}",
            description=f"Activate target control {i+1}",
            grounding=GroundingRequirement(
                target_name="Save Button" if i == 0 else f"Control_{i}",
                semantic_label="Save" if i == 0 else f"Ctrl_{i}",
                preferred_strategy=GroundingStrategy.ACCESSIBILITY,
            ),
        )
        for i in range(step_count)
    ]
    param = SkillParameter(
        parameter_id="param_doc",
        name="document_path",
        type=ParameterType.FILE,
        classification=ValueClassification.PARAMETER,
        description="Path to target document",
        required=True,
        example_value="report.txt",
    )
    ir = SkillIR(
        skill_id=skill_id,
        name=name,
        description="A reusable skill to save active documents.",
        intent_type="DOCUMENT_MANAGEMENT",
        goal=goal,
        parameters=[param],
        steps=steps,
        confidence=0.92,
        provenance={"source_demonstration_ids": ["demo_1001"]},
    )
    ir.fingerprint = ir.compute_canonical_fingerprint()
    return ir


class TestSkillModelsAndSemver:
    """Test model serialization, deserialization, and semantic version parsing."""

    def test_semver_parsing_and_formatting(self):
        maj, min_, pat = parse_semver("1.2.3")
        assert (maj, min_, pat) == (1, 2, 3)
        assert format_semver(1, 2, 3) == "1.2.3"

        with pytest.raises(ValueError):
            parse_semver("1.2")
        with pytest.raises(ValueError):
            parse_semver("v1.0.0")
        with pytest.raises(ValueError):
            parse_semver("invalid")

    def test_skill_record_serialization(self):
        rec = SkillRecord(
            skill_id="skill_001",
            canonical_name="Format Document",
            description="Format text document",
            status=SkillStatus.PUBLISHED,
            current_version="1.0.0",
            versions=["1.0.0"],
            tags=["text", "formatting"],
        )
        d = rec.to_dict()
        assert d["skill_id"] == "skill_001"
        assert d["status"] == "PUBLISHED"

        rec2 = SkillRecord.from_dict(d)
        assert rec2.skill_id == rec.skill_id
        assert rec2.tags == rec.tags

    def test_version_record_and_fingerprint(self):
        ir = make_dummy_ir()
        vrec = SkillVersionRecord(
            skill_id="skill_001",
            version="1.0.0",
            status=SkillStatus.PUBLISHED,
            fingerprint=ir.fingerprint,
            checksum="abc123sha",
            skill_ir=ir,
        )
        assert vrec.compute_version_fingerprint() == ir.fingerprint
        d = vrec.to_dict(include_ir=True)
        assert "skill_ir" in d
        reconstructed = SkillVersionRecord.from_dict(d)
        assert reconstructed.skill_ir is not None
        assert reconstructed.skill_ir.skill_id == ir.skill_id


class TestSkillMemoryStorage:
    """Test atomic storage operations, sandboxing, and immutability."""

    def test_storage_save_load_and_immutability(self, temp_storage):
        storage = SkillMemoryStorage(temp_storage)
        ir = make_dummy_ir()
        vrec = SkillVersionRecord(
            skill_id=ir.skill_id,
            version="1.0.0",
            status=SkillStatus.PUBLISHED,
            fingerprint=ir.fingerprint,
            checksum="",
            skill_ir=ir,
        )

        storage.save_version(vrec)
        assert storage.version_exists(ir.skill_id, "1.0.0")

        # Immutability check: cannot save over existing version
        with pytest.raises(StorageError):
            storage.save_version(vrec)

        loaded = storage.load_version(ir.skill_id, "1.0.0", load_ir=True)
        assert loaded is not None
        assert loaded.skill_id == ir.skill_id
        assert loaded.checksum != ""
        assert loaded.skill_ir is not None
        assert loaded.skill_ir.name == ir.name

    def test_path_traversal_guards(self, temp_storage):
        storage = SkillMemoryStorage(temp_storage)
        with pytest.raises(StorageError):
            storage.get_skill_dir("../etc/passwd")
        with pytest.raises(StorageError):
            storage.get_version_dir("skill_001", "../../root")


class TestSkillComparatorAndBumps:
    """Test semantic diffing and deterministic version bump classifications."""

    def test_patch_classification(self):
        ir_a = make_dummy_ir()
        ir_b = copy.deepcopy(ir_a)
        ir_b.description = "Updated documentation summary."
        diff = SkillComparator.compare("s1", "1.0.0", ir_a, "1.0.1", ir_b)
        assert diff.recommended_bump == VersionBump.PATCH
        assert "No breaking or functional semantic changes" in diff.explanation

    def test_minor_classification_optional_parameter(self):
        ir_a = make_dummy_ir()
        ir_b = copy.deepcopy(ir_a)
        new_param = SkillParameter(
            parameter_id="param_opt",
            name="backup_copy",
            type=ParameterType.BOOLEAN,
            classification=ValueClassification.PARAMETER,
            description="Create backup copy",
            required=False,
            default="false",
        )
        ir_b.parameters.append(new_param)
        diff = SkillComparator.compare("s1", "1.0.0", ir_a, "1.1.0", ir_b)
        assert diff.recommended_bump == VersionBump.MINOR
        assert any("Added optional parameter" in p for p in diff.parameter_changes)

    def test_major_classification_required_parameter(self):
        ir_a = make_dummy_ir()
        ir_b = copy.deepcopy(ir_a)
        new_param = SkillParameter(
            parameter_id="param_req",
            name="mandatory_secret",
            type=ParameterType.STRING,
            classification=ValueClassification.PARAMETER,
            description="Mandatory encryption key",
            required=True,
        )
        ir_b.parameters.append(new_param)
        diff = SkillComparator.compare("s1", "1.0.0", ir_a, "2.0.0", ir_b)
        assert diff.recommended_bump == VersionBump.MAJOR
        assert any("Added required parameter" in p for p in diff.parameter_changes)

    def test_conflict_classification_contradictory_goals(self):
        ir_a = make_dummy_ir(goal="Save the open file to disk")
        ir_b = copy.deepcopy(ir_a)
        ir_b.goal = "Delete the open file from disk"
        diff = SkillComparator.compare("s1", "1.0.0", ir_a, "2.0.0", ir_b)
        assert diff.recommended_bump == VersionBump.CONFLICT
        assert any("Contradictory goals" in s for s in diff.semantic_changes)


class TestSkillMatcher:
    """Test duplicate detection, variant detection, and conflict detection."""

    def test_duplicate_detection(self):
        ir_a = make_dummy_ir(name="Save Document", goal="Save open document")
        ir_b = make_dummy_ir(name="Save Current File", goal="Save open document")
        dup = SkillMatcher.detect_duplicate("s1", "1.0.0", ir_a, "s2", "1.0.0", ir_b)
        assert dup is not None
        assert dup.similarity_score >= 0.85
        assert len(dup.match_reasons) >= 2

    def test_variant_detection(self):
        ir_a = make_dummy_ir(goal="Save active document")
        ir_b = copy.deepcopy(ir_a)
        # Alternate pathway: menu navigation instead of direct button
        ir_b.steps = [
            SkillStep(
                step_id="step_alt_1",
                ordinal=1,
                action_type=SkillActionType.NAVIGATE,
                target="File Menu",
                description="Navigate to file menu",
            ),
            SkillStep(
                step_id="step_alt_2",
                ordinal=2,
                action_type=SkillActionType.ACTIVATE,
                target="Save As...",
                description="Activate Save As menu item",
            ),
        ]
        var = SkillMatcher.detect_variant("s1", "1.0.0", ir_a, "1.1.0", ir_b)
        assert var is not None
        assert "uses [" in var.differing_pathway

    def test_conflict_detection(self):
        ir_a = make_dummy_ir(goal="Create new spreadsheet")
        ir_b = copy.deepcopy(ir_a)
        ir_b.goal = "Delete existing spreadsheet"
        conf = SkillMatcher.detect_conflict("s1", "1.0.0", ir_a, "2.0.0", ir_b)
        assert conf is not None
        assert conf.conflict_type == "CONTRADICTORY_GOALS"


class TestSkillSearch:
    """Test multi-dimensional structured search and ranking."""

    def test_search_ranking(self, temp_storage):
        reg = SkillRegistry(temp_storage)
        ir1 = make_dummy_ir(skill_id="skill_doc_save", name="Save Document", goal="Save file to disk")
        ir2 = make_dummy_ir(skill_id="skill_txt_edit", name="Edit Text", goal="Edit paragraph text")
        reg.register_skill(ir1, initial_version="1.0.0")
        reg.register_skill(ir2, initial_version="1.0.0")

        # Search exact match
        results = reg.search("Save Document")
        assert len(results) >= 1
        assert results[0].skill_id == "skill_doc_save"
        assert results[0].score >= 50.0

        # Search substring
        results_edit = reg.search("Edit")
        assert len(results_edit) >= 1
        assert results_edit[0].skill_id == "skill_txt_edit"


class TestSkillMigration:
    """Test schema migration framework and backward compatibility."""

    def test_legacy_schema_migration(self):
        legacy_data = {
            "skill_id": "skill_legacy",
            "name": "Legacy Skill",
            "description": "Legacy format",
            "status": "PUBLISHED",
            "current_version": "1.0.0",
            "versions": ["1.0.0"],
            "schema_version": "0.9.0",
        }
        assert SkillMigrationManager.is_migration_needed(legacy_data)
        migrated = SkillMigrationManager.migrate_skill_record(legacy_data)
        assert migrated.schema_version == "1.0.0"
        assert migrated.canonical_name == "Legacy Skill"
        assert migrated.tags == []


class TestSkillRegistryLifecycle:
    """Test registry publish, versioning, rollback, archive, and restoration."""

    def test_lifecycle_and_rollbacks(self, temp_storage):
        reg = SkillRegistry(temp_storage)
        ir_v1 = make_dummy_ir(skill_id="skill_lifecycle", name="Lifecycle Skill")
        s_rec, v1_rec = reg.register_skill(ir_v1, initial_version="1.0.0")
        assert s_rec.current_version == "1.0.0"

        # Publish v2
        ir_v2 = copy.deepcopy(ir_v1)
        ir_v2.description = "Updated metadata in v2"
        v2_rec = reg.publish_version(s_rec.skill_id, ir_v2)
        assert v2_rec.version == "1.0.1"
        assert v2_rec.supersedes == "1.0.0"

        # Verify active current version is updated
        updated_s = reg.get_skill(s_rec.skill_id)
        assert updated_s.current_version == "1.0.1"

        # Rollback to v1.0.0
        rolled = reg.rollback_current_version(
            s_rec.skill_id, "1.0.0", reason="Rollback test"
        )
        assert rolled.current_version == "1.0.0"
        rollbacks = reg.storage.load_rollback_history(s_rec.skill_id)
        assert len(rollbacks) == 1
        assert rollbacks[0].previous_current_version == "1.0.1"
        assert rollbacks[0].rollback_target == "1.0.0"

        # Archive and restore
        reg.archive_skill(s_rec.skill_id)
        archived_s = reg.get_skill(s_rec.skill_id)
        assert archived_s.status == SkillStatus.ARCHIVED

        reg.restore_skill(s_rec.skill_id)
        restored_s = reg.get_skill(s_rec.skill_id)
        assert restored_s.status == SkillStatus.PUBLISHED


class TestSkillMemoryValidatorAndSecurity:
    """Test integrity verification, tampered file detection, and payload blocking."""

    def test_checksum_tampering_detection(self, temp_storage):
        reg = SkillRegistry(temp_storage)
        ir = make_dummy_ir(skill_id="skill_tamper_test")
        s_rec, _ = reg.register_skill(ir, initial_version="1.0.0")

        val = SkillMemoryValidator(reg.storage)
        assert len(val.validate_storage_integrity(s_rec.skill_id)) == 0

        # Tamper skill.json directly on disk
        vdir = reg.storage.get_version_dir(s_rec.skill_id, "1.0.0")
        skill_json = vdir / "skill.json"
        skill_json.write_text('{"tampered": true}')

        errs = val.validate_storage_integrity(s_rec.skill_id)
        assert len(errs) >= 1
        assert any("Checksum mismatch" in e for e in errs)

    def test_executable_payload_blocking(self, temp_storage):
        reg = SkillRegistry(temp_storage)
        ir = make_dummy_ir(skill_id="skill_malicious")
        ir.steps[0].target = "pyautogui.click(100, 200)"

        with pytest.raises(StorageError) as exc_info:
            reg.register_skill(ir, initial_version="1.0.0")
        assert "Executable payload violation" in str(exc_info.value)


class TestSemanticBoundary:
    """Strictly verify that Phase 9 does NOT execute or control the user interface."""

    def test_no_execution_apis_in_memory_package(self):
        import teach_a_skill.memory as mem_pkg

        forbidden_methods = [
            "execute_skill",
            "run_skill",
            "replay_skill",
            "click",
            "type",
            "move_mouse",
            "launch_app",
            "run_shell",
            "autonomously_operate_ui",
        ]
        for m in forbidden_methods:
            assert not hasattr(mem_pkg, m), f"Boundary violation: {m} exists in Phase 9!"


class TestAuthoritativeRealDataVerification:
    """Verify registration, versioning, and immutability with real Phase 8 skill on session_485fc80a."""

    def test_real_data_phase8_skill_registration(self):
        app = TeachSkillApp(quiet=True)
        app.initialize()
        sm = app.storage_manager
        session_id = "session_485fc80a"

        session_dir = sm.get_path("recordings", session_id)
        if not session_dir.exists():
            pytest.skip(f"Authoritative session '{session_id}' not found.")

        skill_file = session_dir / "skill" / "skill.json"
        if not skill_file.is_file():
            # Compile first if not compiled
            from teach_a_skill.skill.pipeline import SkillCompilationPipeline
            pipe = SkillCompilationPipeline(sm)
            pipe.compile_session(session_id)

        # 1. Record pre-hashes of all Phase 2-8 files
        pre_hashes: dict[str, str] = {}
        for sub in ["canonical", "perception", "multimodal", "intent", "skill", "video", "frames"]:
            sub_dir = session_dir / sub
            if sub_dir.exists():
                for p in sub_dir.rglob("*"):
                    if p.is_file():
                        pre_hashes[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()

        assert len(pre_hashes) > 0

        # 2. Register Phase 8 skill into Registry
        reg = SkillRegistry(sm)
        import json
        with open(skill_file, "r", encoding="utf-8") as f:
            skill_ir = SkillIR.from_dict(json.load(f))

        s_rec, v1_rec = reg.register_skill(
            skill_ir=skill_ir,
            initial_version="1.0.0",
            source_demo_id=session_id,
        )

        assert s_rec.skill_id.startswith("skill_")
        assert v1_rec.version == "1.0.0"
        assert v1_rec.checksum != ""
        assert len(v1_rec.fingerprint) == 64

        # 3. Publish derived version 1.0.1 (PATCH metadata update) if not already present
        if not reg.storage.version_exists(s_rec.skill_id, "1.0.1"):
            skill_ir_v2 = copy.deepcopy(skill_ir)
            skill_ir_v2.description = "Refined description for real session demonstration."
            v2_rec = reg.publish_version(s_rec.skill_id, skill_ir_v2, explicit_version="1.0.1")
            assert v2_rec.version == "1.0.1"
        else:
            v2_rec = reg.get_version(s_rec.skill_id, "1.0.1")
            assert v2_rec is not None

        # Compare v1.0.0 and v1.0.1
        diff = reg.compare_versions(s_rec.skill_id, "1.0.0", "1.0.1")
        assert diff.recommended_bump == VersionBump.PATCH

        # 4. Verify Immutability of earlier phases
        post_hashes: dict[str, str] = {}
        for filepath_str in pre_hashes:
            post_hashes[filepath_str] = hashlib.sha256(Path(filepath_str).read_bytes()).hexdigest()

        for filepath_str, pre_hash in pre_hashes.items():
            assert post_hashes[filepath_str] == pre_hash, f"Immutability violation on {filepath_str}!"


class TestBenchmarkRunner:
    """Test performance, scaling, and stress benchmarks."""

    def test_benchmark_runner_execution(self, temp_storage):
        from teach_a_skill.memory.benchmark import SkillMemoryBenchmarkRunner
        runner = SkillMemoryBenchmarkRunner(temp_storage)

        core_res = runner.run_core_benchmarks()
        assert len(core_res) == 5
        for item in core_res:
            assert item.status == "PASS"

        scale_res = runner.run_scaling_benchmark(20)
        assert scale_res.status == "PASS"

        stress_res = runner.run_long_run_memory_test(iterations=10)
        assert stress_res.status == "PASS"
