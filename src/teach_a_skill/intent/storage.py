"""Storage manager for Phase 7 semantic intent and demonstration understanding artifacts."""

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Optional

from teach_a_skill.core.logging import get_logger
from teach_a_skill.intent.models import (
    DemonstratedIntent,
    DemonstrationUnderstanding,
    IntentManifest,
    SemanticAction,
    TaskEntity,
    TaskStage,
)
from teach_a_skill.storage.manager import StorageManager

logger = get_logger("teach_a_skill.intent.storage")


class IntentStorage:
    """Manages atomic persistence, retrieval, and integrity verification of Phase 7 intent artifacts."""

    def __init__(self, storage_manager: StorageManager, session_id: str) -> None:
        self.storage_manager = storage_manager
        self.session_id = session_id
        self.session_dir = storage_manager.get_path("recordings", session_id)
        self.intent_dir = self.session_dir / "intent"
        self.staging_dir = self.session_dir / ".intent_staging"

    def exists(self) -> bool:
        """Check if complete intent artifacts already exist for this session."""
        manifest_file = self.intent_dir / "manifest.json"
        tasks_file = self.intent_dir / "tasks.jsonl"
        return manifest_file.exists() and tasks_file.exists()

    def read_manifest(self) -> Optional[IntentManifest]:
        """Read intent manifest."""
        manifest_file = self.intent_dir / "manifest.json"
        if not manifest_file.exists():
            return None
        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return IntentManifest.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to read intent manifest for {self.session_id}: {e}")
            return None

    def read_tasks(self) -> list[DemonstrationUnderstanding]:
        """Read all demonstration understanding tasks from tasks.jsonl."""
        tasks_file = self.intent_dir / "tasks.jsonl"
        if not tasks_file.exists():
            return []
        tasks: list[DemonstrationUnderstanding] = []
        with open(tasks_file, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    tasks.append(DemonstrationUnderstanding.from_dict(json.loads(line)))
                except Exception as e:
                    logger.warning(f"Corrupted task line {line_no} in {tasks_file}: {e}")
        return tasks

    def read_intent(self) -> Optional[DemonstratedIntent]:
        """Read primary demonstrated intent from intent.jsonl."""
        intent_file = self.intent_dir / "intent.jsonl"
        if not intent_file.exists():
            return None
        try:
            with open(intent_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        return DemonstratedIntent.from_dict(json.loads(line))
        except Exception as e:
            logger.warning(f"Failed to read intent from {intent_file}: {e}")
        return None

    def read_stages(self) -> list[TaskStage]:
        """Read all task stages from stages.jsonl."""
        stages_file = self.intent_dir / "stages.jsonl"
        if not stages_file.exists():
            return []
        stages: list[TaskStage] = []
        with open(stages_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        stages.append(TaskStage.from_dict(json.loads(line)))
                    except Exception:
                        pass
        return stages

    def read_actions(self) -> list[SemanticAction]:
        """Read all semantic actions from actions.jsonl."""
        actions_file = self.intent_dir / "actions.jsonl"
        if not actions_file.exists():
            return []
        actions: list[SemanticAction] = []
        with open(actions_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        actions.append(SemanticAction.from_dict(json.loads(line)))
                    except Exception:
                        pass
        return actions

    def read_entities(self) -> list[TaskEntity]:
        """Read all task entities from entities.jsonl."""
        entities_file = self.intent_dir / "entities.jsonl"
        if not entities_file.exists():
            return []
        entities: list[TaskEntity] = []
        with open(entities_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entities.append(TaskEntity.from_dict(json.loads(line)))
                    except Exception:
                        pass
        return entities

    def read_checksums(self) -> dict[str, str]:
        """Read checksums.json dictionary."""
        checksums_file = self.intent_dir / "checksums.json"
        if not checksums_file.exists():
            return {}
        try:
            with open(checksums_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def write_intent_artifacts(
        self,
        understanding: DemonstrationUnderstanding,
        manifest: IntentManifest,
    ) -> None:
        """Persist intent artifacts atomically via staging directory."""
        if self.staging_dir.exists():
            shutil.rmtree(self.staging_dir, ignore_errors=True)

        self.staging_dir.mkdir(parents=True, exist_ok=True)
        indexes_dir = self.staging_dir / "indexes"
        indexes_dir.mkdir(parents=True, exist_ok=True)

        intent_path = self.staging_dir / "intent.jsonl"
        tasks_path = self.staging_dir / "tasks.jsonl"
        stages_path = self.staging_dir / "stages.jsonl"
        actions_path = self.staging_dir / "actions.jsonl"
        entities_path = self.staging_dir / "entities.jsonl"
        manifest_path = self.staging_dir / "manifest.json"
        checksums_path = self.staging_dir / "checksums.json"
        index_path = indexes_dir / "intent_index.json"

        # 1. Write intent.jsonl
        with open(intent_path, "w", encoding="utf-8") as f:
            if understanding.primary_intent:
                f.write(json.dumps(understanding.primary_intent.to_dict()) + "\n")

        # 2. Write tasks.jsonl
        with open(tasks_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(understanding.to_dict()) + "\n")

        # 3. Write stages.jsonl
        with open(stages_path, "w", encoding="utf-8") as f:
            for stage in understanding.stages:
                f.write(json.dumps(stage.to_dict()) + "\n")

        # 4. Write actions.jsonl
        with open(actions_path, "w", encoding="utf-8") as f:
            for action in understanding.actions:
                f.write(json.dumps(action.to_dict()) + "\n")

        # 5. Write entities.jsonl
        with open(entities_path, "w", encoding="utf-8") as f:
            for entity in understanding.entities:
                f.write(json.dumps(entity.to_dict()) + "\n")

        # 6. Build index
        index_data = {
            "task_id": understanding.task_id,
            "session_id": understanding.session_id,
            "goal": understanding.goal,
            "stages_by_id": {s.stage_id: s.to_dict() for s in understanding.stages},
            "actions_by_id": {a.action_id: a.to_dict() for a in understanding.actions},
            "entities_by_id": {e.entity_id: e.to_dict() for e in understanding.entities},
            "actions_by_type": {},
            "entities_by_type": {},
        }
        for act in understanding.actions:
            index_data["actions_by_type"].setdefault(str(act.action_type), []).append(act.action_id)
        for ent in understanding.entities:
            index_data["entities_by_type"].setdefault(ent.entity_type, []).append(ent.entity_id)

        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index_data, f, indent=2)

        # 7. Write manifest.json
        manifest.total_stages = len(understanding.stages)
        manifest.total_actions = len(understanding.actions)
        manifest.total_entities = len(understanding.entities)
        manifest.total_ambiguities = len(understanding.ambiguities)
        if understanding.primary_intent:
            manifest.primary_intent_type = str(understanding.primary_intent.intent_type)
        manifest.overall_confidence = understanding.confidence

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest.to_dict(), f, indent=2)

        # 8. Compute and write checksums.json for all files in staging (except checksums.json itself)
        checksums: dict[str, str] = {}
        for p in sorted(self.staging_dir.rglob("*")):
            if p.is_file() and p.name != "checksums.json":
                rel = p.relative_to(self.staging_dir).as_posix()
                with open(p, "rb") as bf:
                    checksums[rel] = hashlib.sha256(bf.read()).hexdigest()

        with open(checksums_path, "w", encoding="utf-8") as f:
            json.dump(checksums, f, indent=2)

        # 9. Atomic swap
        if self.intent_dir.exists():
            shutil.rmtree(self.intent_dir)
        self.staging_dir.replace(self.intent_dir)
        logger.info(f"Atomically persisted Phase 7 intent artifacts to {self.intent_dir}")
