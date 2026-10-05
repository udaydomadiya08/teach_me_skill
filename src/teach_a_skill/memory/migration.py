"""Schema migration framework for persistent Skill Memory.

Supports schema evolution without mutating or corrupting historical, immutable version files.
"""

from __future__ import annotations

import copy
import logging
from typing import Any

from teach_a_skill.core.errors import StorageError
from teach_a_skill.memory.models import SkillRecord, SkillVersionRecord

logger = logging.getLogger(__name__)


class SkillMigrationManager:
    """Manages schema migrations for SkillRecord and SkillVersionRecord."""

    CURRENT_SCHEMA_VERSION = "1.0.0"
    SUPPORTED_SCHEMA_VERSIONS = {"0.9.0", "1.0.0", "1.1.0"}

    @classmethod
    def is_migration_needed(cls, data: dict[str, Any]) -> bool:
        """Check if dictionary payload requires schema migration."""
        version = data.get("schema_version", "1.0.0")
        return version != cls.CURRENT_SCHEMA_VERSION

    @classmethod
    def migrate_skill_record(cls, data: dict[str, Any]) -> SkillRecord:
        """Migrate a raw skill record dictionary to the current schema."""
        source_ver = data.get("schema_version", "1.0.0")
        if source_ver not in cls.SUPPORTED_SCHEMA_VERSIONS:
            raise StorageError(
                f"Unsupported schema version '{source_ver}'. Cannot migrate skill record."
            )

        migrated = copy.deepcopy(data)

        # Example migration from 0.9.0 -> 1.0.0
        if source_ver == "0.9.0":
            if "name" in migrated and "canonical_name" not in migrated:
                migrated["canonical_name"] = migrated.pop("name")
            if "tags" not in migrated:
                migrated["tags"] = []
            if "capabilities" not in migrated:
                migrated["capabilities"] = []
            if "dependencies" not in migrated:
                migrated["dependencies"] = []
            migrated["schema_version"] = cls.CURRENT_SCHEMA_VERSION

        return SkillRecord.from_dict(migrated)

    @classmethod
    def migrate_version_record(cls, data: dict[str, Any]) -> SkillVersionRecord:
        """Migrate a raw version record dictionary to current schema."""
        source_ver = data.get("schema_version", "1.0.0")
        if source_ver not in cls.SUPPORTED_SCHEMA_VERSIONS:
            raise StorageError(
                f"Unsupported version schema '{source_ver}'. Cannot migrate version record."
            )

        migrated = copy.deepcopy(data)
        if source_ver == "0.9.0":
            if "checksum" not in migrated:
                migrated["checksum"] = ""
            migrated["schema_version"] = cls.CURRENT_SCHEMA_VERSION

        return SkillVersionRecord.from_dict(migrated)
