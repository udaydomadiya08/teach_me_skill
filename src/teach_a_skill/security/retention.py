"""Centralized retention policy enforcement across all storage partitions."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from teach_a_skill.interfaces.storage import IStorageManager


@dataclass
class RetentionPolicy:
    """Centralized retention limits (in days) for all system artifacts."""

    recordings_days: int = 30
    screenshots_days: int = 14
    audio_days: int = 14
    transcripts_days: int = 30
    timelines_days: int = 30
    perception_days: int = 14
    execution_records_days: int = 60
    recovery_records_days: int = 60
    learning_records_days: int = 90
    audit_records_days: int = 365
    model_cache_days: int = 7
    skills_retained_indefinitely: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RetentionManager:
    """Applies centralized retention rules and cleans up expired artifacts safely."""

    def __init__(self, storage_manager: IStorageManager, policy: Optional[RetentionPolicy] = None) -> None:
        self.storage = storage_manager
        self.policy = policy or RetentionPolicy()

    def scan_expired_files(self) -> dict[str, list[Path]]:
        """Identify expired artifacts across categories based on mtime and policy."""
        now = time.time()
        expired: dict[str, list[Path]] = {}

        category_limits = {
            "recordings": self.policy.recordings_days,
            "perception": self.policy.perception_days,
            "execution": self.policy.execution_records_days,
            "recovery": self.policy.recovery_records_days,
            "learning": self.policy.learning_records_days,
            "models": self.policy.model_cache_days,
        }

        for cat, days in category_limits.items():
            cat_path = self.storage.get_path(cat)
            expired[cat] = []
            if not cat_path.exists():
                continue

            cutoff = now - (days * 86400)
            for f in cat_path.rglob("*"):
                if f.is_file() and not f.name.startswith("."):
                    try:
                        if f.stat().st_mtime < cutoff:
                            expired[cat].append(f)
                    except Exception:
                        pass

        return expired

    def enforce_retention(self) -> dict[str, int]:
        """Prune expired files safely. Never deletes active skills or unbroken audit logs."""
        expired = self.scan_expired_files()
        pruned_counts: dict[str, int] = {}

        for cat, file_list in expired.items():
            count = 0
            for f in file_list:
                try:
                    f.unlink()
                    count += 1
                except Exception:
                    pass
            pruned_counts[cat] = count

        return pruned_counts
