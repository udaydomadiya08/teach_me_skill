"""Versioned, atomic, idempotent data migration manager for Phase 14."""

from __future__ import annotations

import copy
import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from teach_a_skill.core.errors import TeachSkillError


class MigrationError(TeachSkillError):
    """Raised when a versioned data migration fails or causes regression."""
    pass


@dataclass(frozen=True)
class MigrationStep:
    """Defined schema migration unit."""

    migration_id: str
    target_component: str  # "config", "storage", "skill_ir", "learning"
    from_version: str
    to_version: str
    description: str
    is_idempotent: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MigrationManager:
    """Orchestrates atomic schema migrations across configuration, skill memory, and learning records."""

    def __init__(self, migration_state_file: Optional[Path | str] = None) -> None:
        self.state_file = Path(migration_state_file) if migration_state_file else None
        self._history: list[dict[str, Any]] = []

    def get_available_migrations(self) -> list[MigrationStep]:
        """List canonical registered schema migrations."""
        return [
            MigrationStep(
                migration_id="mig_001_config_v1",
                target_component="config",
                from_version="0.1.0",
                to_version="1.0.0",
                description="Migrate legacy flat config to namespaced privacy and security schema",
            ),
            MigrationStep(
                migration_id="mig_002_skill_ir_v1",
                target_component="skill_ir",
                from_version="0.9.0",
                to_version="1.0.0",
                description="Upgrade SkillIR steps to explicit semantic target elements and bounds",
            ),
            MigrationStep(
                migration_id="mig_003_learning_v1",
                target_component="learning",
                from_version="0.5.0",
                to_version="1.0.0",
                description="Add cryptographic fingerprint and provenance to execution records",
            ),
        ]

    def migrate_config(self, raw_config: dict[str, Any], target_version: str = "1.0.0") -> dict[str, Any]:
        """Upgrade configuration dictionary to current schema version idempotently."""
        migrated = copy.deepcopy(raw_config)
        curr = str(migrated.get("version", "0.1.0"))
        if curr == target_version:
            return migrated

        # Apply mig_001
        migrated.setdefault("privacy", {
            "local_only": True,
            "allow_network": False,
            "telemetry_enabled": False,
            "cloud_inference": False,
        })
        migrated.setdefault("security", {
            "least_privilege": True,
            "audit_integrity": True,
            "sandbox_boundaries": True,
        })
        migrated["version"] = target_version
        self._record_migration("mig_001_config_v1", "config", curr, target_version)
        return migrated

    def migrate_storage_directory(self, storage_dir: Path | str, backup: bool = True) -> dict[str, Any]:
        """Execute atomic directory migration with automatic rollback on failure."""
        sdir = Path(storage_dir)
        if not sdir.exists():
            return {"status": "SKIPPED", "reason": "Directory does not exist"}

        backup_dir = None
        if backup:
            backup_dir = sdir.parent / f"{sdir.name}_backup_migration"
            if backup_dir.exists():
                shutil.rmtree(backup_dir)
            shutil.copytree(sdir, backup_dir)

        try:
            # Upgrade partition directory structure
            for sub in ("skills", "memory", "learning", "audits", "recordings", ".tmp"):
                (sdir / sub).mkdir(parents=True, exist_ok=True)

            # Record migration marker
            version_marker = sdir / ".storage_version"
            version_marker.write_text(json.dumps({"schema_version": "1.0.0", "migrated_at": datetime.now(timezone.utc).isoformat()}))

            return {
                "status": "MIGRATED_SUCCESSFULLY",
                "schema_version": "1.0.0",
                "backup_path": str(backup_dir) if backup_dir else None,
            }
        except Exception as e:
            # Rollback to backup
            if backup_dir and backup_dir.exists():
                shutil.rmtree(sdir)
                shutil.copytree(backup_dir, sdir)
            raise MigrationError(f"Storage migration failed and was rolled back: {e}")

    def _record_migration(self, mig_id: str, component: str, from_v: str, to_v: str) -> None:
        rec = {
            "migration_id": mig_id,
            "component": component,
            "from_version": from_v,
            "to_version": to_v,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._history.append(rec)

    def get_history(self) -> list[dict[str, Any]]:
        return list(self._history)
