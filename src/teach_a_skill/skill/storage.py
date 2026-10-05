"""Storage manager for Phase 8 Skill IR artifacts."""

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Optional

from teach_a_skill.core.logging import get_logger
from teach_a_skill.skill.models import (
    SkillCheckpoint,
    SkillDependency,
    SkillIR,
    SkillManifest,
    SkillParameter,
    SkillStep,
    SkillVariable,
)
from teach_a_skill.storage.manager import StorageManager

logger = get_logger("teach_a_skill.skill.storage")


class SkillStorage:
    """Manages atomic persistence, retrieval, and integrity verification of Phase 8 Skill IR artifacts."""

    def __init__(self, storage_manager: StorageManager, session_id: str) -> None:
        self.storage_manager = storage_manager
        self.session_id = session_id
        self.session_dir = storage_manager.get_path("recordings", session_id)
        self.skill_dir = self.session_dir / "skill"
        self.staging_dir = self.session_dir / ".skill_staging"

    def exists(self) -> bool:
        """Check if complete skill artifacts exist for this session."""
        manifest_file = self.skill_dir / "manifest.json"
        skill_file = self.skill_dir / "skill.json"
        return manifest_file.exists() and skill_file.exists()

    def read_manifest(self) -> Optional[SkillManifest]:
        """Read skill compilation manifest."""
        manifest_file = self.skill_dir / "manifest.json"
        if not manifest_file.exists():
            return None
        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                return SkillManifest.from_dict(json.load(f))
        except Exception as e:
            logger.error(f"Failed to read skill manifest for {self.session_id}: {e}")
            return None

    def read_skill(self) -> Optional[SkillIR]:
        """Read Skill IR from skill.json."""
        skill_file = self.skill_dir / "skill.json"
        if not skill_file.exists():
            return None
        try:
            with open(skill_file, "r", encoding="utf-8") as f:
                return SkillIR.from_dict(json.load(f))
        except Exception as e:
            logger.error(f"Failed to read skill.json for {self.session_id}: {e}")
            return None

    def read_steps(self) -> list[SkillStep]:
        """Read all skill steps from steps.jsonl."""
        steps_file = self.skill_dir / "steps.jsonl"
        if not steps_file.exists():
            return []
        steps: list[SkillStep] = []
        with open(steps_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        steps.append(SkillStep.from_dict(json.loads(line)))
                    except Exception:
                        pass
        return sorted(steps, key=lambda s: s.ordinal)

    def read_parameters(self) -> list[SkillParameter]:
        """Read all parameters from parameters.jsonl."""
        param_file = self.skill_dir / "parameters.jsonl"
        if not param_file.exists():
            return []
        params: list[SkillParameter] = []
        with open(param_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        params.append(SkillParameter.from_dict(json.loads(line)))
                    except Exception:
                        pass
        return params

    def read_variables(self) -> list[SkillVariable]:
        """Read all variables from variables.jsonl."""
        var_file = self.skill_dir / "variables.jsonl"
        if not var_file.exists():
            return []
        vars_list: list[SkillVariable] = []
        with open(var_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        vars_list.append(SkillVariable.from_dict(json.loads(line)))
                    except Exception:
                        pass
        return vars_list

    def read_checkpoints(self) -> list[SkillCheckpoint]:
        """Read all checkpoints from checkpoints.jsonl."""
        chk_file = self.skill_dir / "checkpoints.jsonl"
        if not chk_file.exists():
            return []
        checkpoints: list[SkillCheckpoint] = []
        with open(chk_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        checkpoints.append(SkillCheckpoint.from_dict(json.loads(line)))
                    except Exception:
                        pass
        return checkpoints

    def read_dependencies(self) -> list[SkillDependency]:
        """Read all dependencies from dependencies.jsonl."""
        dep_file = self.skill_dir / "dependencies.jsonl"
        if not dep_file.exists():
            return []
        dependencies: list[SkillDependency] = []
        with open(dep_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        dependencies.append(SkillDependency.from_dict(json.loads(line)))
                    except Exception:
                        pass
        return dependencies

    def read_checksums(self) -> dict[str, str]:
        """Read checksums.json dictionary."""
        checksums_file = self.skill_dir / "checksums.json"
        if not checksums_file.exists():
            return {}
        try:
            with open(checksums_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def write_skill_artifacts(
        self,
        skill: SkillIR,
        manifest: SkillManifest,
    ) -> None:
        """Persist compiled Skill IR artifacts atomically via staging directory."""
        if self.staging_dir.exists():
            shutil.rmtree(self.staging_dir, ignore_errors=True)

        self.staging_dir.mkdir(parents=True, exist_ok=True)
        indexes_dir = self.staging_dir / "indexes"
        indexes_dir.mkdir(parents=True, exist_ok=True)

        skill_path = self.staging_dir / "skill.json"
        steps_path = self.staging_dir / "steps.jsonl"
        parameters_path = self.staging_dir / "parameters.jsonl"
        variables_path = self.staging_dir / "variables.jsonl"
        checkpoints_path = self.staging_dir / "checkpoints.jsonl"
        dependencies_path = self.staging_dir / "dependencies.jsonl"
        manifest_path = self.staging_dir / "manifest.json"
        checksums_path = self.staging_dir / "checksums.json"
        index_path = indexes_dir / "skill_index.json"

        # 1. skill.json
        with open(skill_path, "w", encoding="utf-8") as f:
            json.dump(skill.to_dict(), f, indent=2)

        # 2. steps.jsonl
        with open(steps_path, "w", encoding="utf-8") as f:
            for step in skill.steps:
                f.write(json.dumps(step.to_dict()) + "\n")

        # 3. parameters.jsonl
        with open(parameters_path, "w", encoding="utf-8") as f:
            for param in skill.parameters:
                f.write(json.dumps(param.to_dict()) + "\n")

        # 4. variables.jsonl
        with open(variables_path, "w", encoding="utf-8") as f:
            for var in skill.variables:
                f.write(json.dumps(var.to_dict()) + "\n")

        # 5. checkpoints.jsonl
        with open(checkpoints_path, "w", encoding="utf-8") as f:
            for chk in skill.checkpoints:
                f.write(json.dumps(chk.to_dict()) + "\n")

        # 6. dependencies.jsonl
        with open(dependencies_path, "w", encoding="utf-8") as f:
            for dep in skill.dependencies:
                f.write(json.dumps(dep.to_dict()) + "\n")

        # 7. indexes/skill_index.json
        index_data = {
            "skill_id": skill.skill_id,
            "fingerprint": skill.fingerprint,
            "steps_by_id": {s.step_id: s.to_dict() for s in skill.steps},
            "parameters_by_id": {p.parameter_id: p.to_dict() for p in skill.parameters},
            "steps_by_action_type": {},
        }
        for s in skill.steps:
            index_data["steps_by_action_type"].setdefault(str(s.action_type), []).append(s.step_id)

        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index_data, f, indent=2)

        # 8. manifest.json
        manifest.skill_id = skill.skill_id
        manifest.fingerprint = skill.fingerprint
        manifest.status = str(skill.status)
        manifest.total_steps = len(skill.steps)
        manifest.total_parameters = len(skill.parameters)
        manifest.total_variables = len(skill.variables)
        manifest.total_checkpoints = len(skill.checkpoints)
        manifest.total_dependencies = len(skill.dependencies)
        manifest.overall_confidence = skill.confidence

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest.to_dict(), f, indent=2)

        # 9. Compute and write checksums.json
        checksums: dict[str, str] = {}
        for p in sorted(self.staging_dir.rglob("*")):
            if p.is_file() and p.name != "checksums.json":
                rel = p.relative_to(self.staging_dir).as_posix()
                with open(p, "rb") as bf:
                    checksums[rel] = hashlib.sha256(bf.read()).hexdigest()

        with open(checksums_path, "w", encoding="utf-8") as f:
            json.dump(checksums, f, indent=2)

        # 10. Atomic promotion
        if self.skill_dir.exists():
            shutil.rmtree(self.skill_dir)
        self.staging_dir.replace(self.skill_dir)
        logger.info(f"Atomically promoted Phase 8 Skill IR to {self.skill_dir}")
