"""Content-addressed compilation and comparison cache for Skill Memory.

Caches expensive semantic diffs, duplicate detection comparisons, and search indexes.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Optional

from teach_a_skill.interfaces.storage import IStorageManager
from teach_a_skill.memory.models import VersionDiff

logger = logging.getLogger(__name__)


class SkillMemoryCache:
    """Content-addressed cache for skill comparisons, diffs, and query results."""

    CACHE_ALGORITHM_VERSION = "1.0.0"

    def __init__(self, storage_manager: IStorageManager) -> None:
        self.cache_dir = storage_manager.get_path("cache") / "skill_memory"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._mem_cache: dict[str, Any] = {}

    def _make_key(self, prefix: str, *components: str) -> str:
        raw = f"{prefix}:{self.CACHE_ALGORITHM_VERSION}:" + ":".join(components)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get_diff(self, fingerprint_a: str, fingerprint_b: str) -> Optional[dict[str, Any]]:
        """Retrieve cached VersionDiff dict by operand fingerprints."""
        key = self._make_key("diff", fingerprint_a, fingerprint_b)
        if key in self._mem_cache:
            return self._mem_cache[key]

        cache_file = self.cache_dir / f"diff_{key}.json"
        if cache_file.is_file():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._mem_cache[key] = data
                return data
            except Exception:
                return None
        return None

    def put_diff(self, fingerprint_a: str, fingerprint_b: str, diff: VersionDiff) -> None:
        """Store VersionDiff in content-addressed cache."""
        key = self._make_key("diff", fingerprint_a, fingerprint_b)
        diff_dict = diff.to_dict()
        self._mem_cache[key] = diff_dict

        cache_file = self.cache_dir / f"diff_{key}.json"
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(diff_dict, f, indent=2, sort_keys=True)
        except Exception as e:
            logger.warning(f"Failed to persist cache entry for key '{key}': {e}")

    def clear(self) -> None:
        """Clear memory and on-disk cache."""
        self._mem_cache.clear()
        if self.cache_dir.exists():
            for p in self.cache_dir.glob("*.json"):
                try:
                    p.unlink()
                except Exception:
                    pass
