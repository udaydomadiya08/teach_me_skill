"""Compilation pipeline coordinating semantic reading, compilation, validation, and storage."""

import hashlib
import time
from typing import Optional

from teach_a_skill.core.logging import get_logger
from teach_a_skill.hardware.tiers import HardwareTier
from teach_a_skill.intent.storage import IntentStorage
from teach_a_skill.skill.cache import SkillCache
from teach_a_skill.skill.compilers.base import SkillCompiler
from teach_a_skill.skill.compilers.registry import CompilerRegistry
from teach_a_skill.skill.models import SkillIR, SkillManifest
from teach_a_skill.skill.storage import SkillStorage
from teach_a_skill.skill.validator import SkillValidator
from teach_a_skill.storage.manager import StorageManager

logger = get_logger("teach_a_skill.skill.pipeline")


class SkillCompilationPipeline:
    """Coordinates compilation of Phase 7 demonstration understanding into portable Skill IR."""

    def __init__(
        self,
        storage_manager: StorageManager,
        compiler: Optional[SkillCompiler] = None,
        compiler_name: Optional[str] = None,
        cache_enabled: bool = True,
        hardware_tier: Optional[HardwareTier] = None,
    ) -> None:
        self.storage_manager = storage_manager
        self.registry = CompilerRegistry(hardware_tier=hardware_tier)
        if compiler:
            self.compiler = compiler
        else:
            self.compiler = self.registry.select_best_compiler(preferred_compiler=compiler_name)

        cache_dir = storage_manager.get_path("cache", "skill")
        self.cache = SkillCache(cache_dir=cache_dir) if cache_enabled else None
        self.validator = SkillValidator()

    def compile_session(
        self,
        session_id: str,
        force_rebuild: bool = False,
    ) -> tuple[SkillIR, SkillManifest]:
        """Compile Phase 7 demonstration understanding for a given session into Skill IR."""
        storage = SkillStorage(self.storage_manager, session_id)
        if not force_rebuild and storage.exists():
            manifest = storage.read_manifest()
            skill = storage.read_skill()
            if manifest and skill:
                logger.info(f"Phase 8 Skill IR already exists for session '{session_id}'. Reusing existing.")
                return skill, manifest

        start_time = time.perf_counter()
        logger.info(
            f"Compiling demonstration session '{session_id}' using compiler '{self.compiler.capabilities.compiler_id}'..."
        )

        # 1. Read Phase 7 Demonstration Understanding
        intent_storage = IntentStorage(self.storage_manager, session_id)
        if not intent_storage.exists():
            raise RuntimeError(
                f"Phase 7 intent artifacts not found for session '{session_id}'. "
                "Run 'teach-skill intent analyze <session>' first."
            )

        tasks = intent_storage.read_tasks()
        if not tasks:
            raise RuntimeError(f"No task understanding found in Phase 7 intent partition for '{session_id}'.")
        understanding = tasks[0]

        # 2. Compute semantic fingerprint for cache lookup
        sem_fp = understanding.primary_intent.fingerprint if understanding.primary_intent else ""
        if not sem_fp:
            sem_fp = hashlib.sha256(f"{understanding.task_id}:{understanding.goal}".encode("utf-8")).hexdigest()

        # 3. Check Cache
        cache_key = None
        skill_ir: Optional[SkillIR] = None
        if self.cache:
            cache_key = self.cache.compute_cache_key(
                session_id=session_id,
                semantic_fingerprint=sem_fp,
                compiler_id=self.compiler.capabilities.compiler_id,
                compiler_version=self.compiler.capabilities.compiler_version,
            )
            skill_ir = self.cache.get(cache_key)

        # 4. Compile if cache miss
        if skill_ir is None:
            skill_ir = self.compiler.compile(understanding)

            # Strict validation
            validation_errors = self.validator.validate(skill_ir)
            if validation_errors:
                raise ValueError(
                    f"Skill compilation validation failed with {len(validation_errors)} error(s): "
                    + "; ".join(validation_errors)
                )

            if self.cache and cache_key:
                self.cache.put(cache_key, skill_ir)

        duration = time.perf_counter() - start_time

        # 5. Build Manifest
        manifest = SkillManifest(
            manifest_id=f"manifest_skill_{session_id}",
            skill_id=skill_ir.skill_id,
            session_id=session_id,
            schema_version="1.0.0",
            compiler_id=self.compiler.capabilities.compiler_id,
            compiler_version=self.compiler.capabilities.compiler_version,
            status=str(skill_ir.status),
            total_steps=len(skill_ir.steps),
            total_parameters=len(skill_ir.parameters),
            total_variables=len(skill_ir.variables),
            total_checkpoints=len(skill_ir.checkpoints),
            total_dependencies=len(skill_ir.dependencies),
            overall_confidence=skill_ir.confidence,
            fingerprint=skill_ir.fingerprint,
            compilation_duration_sec=round(duration, 4),
            metadata={
                "source_demonstration_id": session_id,
                "compiler_category": str(self.compiler.capabilities.category),
            },
        )

        # 6. Persist Atomically
        storage.write_skill_artifacts(skill=skill_ir, manifest=manifest)
        logger.info(f"Phase 8 Skill compilation completed for session '{session_id}' in {duration:.3f}s")

        return skill_ir, manifest
