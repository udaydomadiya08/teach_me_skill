"""Execution cache: content-addressed caching for grounding and plan results."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ExecutionCache:
    """Content-addressed on-disk cache for grounding and plan results."""

    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _key(self, *parts: str) -> str:
        """Compute a cache key from string parts."""
        payload = "|".join(parts)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def put_grounding(
        self, skill_id: str, step_id: str, snapshot_hash: str, result: dict[str, Any]
    ) -> None:
        """Cache a grounding result."""
        key = self._key("grounding", skill_id, step_id, snapshot_hash)
        path = self.cache_dir / f"{key}.json"
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, sort_keys=True)
        except Exception as e:
            logger.warning("Failed to write grounding cache: %s", e)

    def get_grounding(
        self, skill_id: str, step_id: str, snapshot_hash: str
    ) -> Optional[dict[str, Any]]:
        """Retrieve a cached grounding result."""
        key = self._key("grounding", skill_id, step_id, snapshot_hash)
        path = self.cache_dir / f"{key}.json"
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Failed to read grounding cache: %s", e)
            return None

    def put_plan(self, plan_fingerprint: str, plan: dict[str, Any]) -> None:
        """Cache an execution plan."""
        key = self._key("plan", plan_fingerprint)
        path = self.cache_dir / f"{key}.json"
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(plan, f, indent=2, sort_keys=True)
        except Exception as e:
            logger.warning("Failed to write plan cache: %s", e)

    def get_plan(self, plan_fingerprint: str) -> Optional[dict[str, Any]]:
        """Retrieve a cached execution plan."""
        key = self._key("plan", plan_fingerprint)
        path = self.cache_dir / f"{key}.json"
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Failed to read plan cache: %s", e)
            return None

    def clear(self) -> int:
        """Clear all cached entries. Returns count of entries removed."""
        count = 0
        for f in self.cache_dir.glob("*.json"):
            f.unlink()
            count += 1
        return count
