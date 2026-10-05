"""Content-addressed semantic intent inference cache."""

import hashlib
import json
from pathlib import Path
from typing import Any, Optional

from teach_a_skill.core.logging import get_logger
from teach_a_skill.intent.models import DemonstrationUnderstanding

logger = get_logger("teach_a_skill.intent.cache")


class IntentCache:
    """Content-addressed cache for semantic task understanding and intent inference results."""

    def __init__(
        self,
        cache_dir: Path,
        max_entries: int = 1000,
        schema_version: str = "1.0.0",
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.max_entries = max_entries
        self.schema_version = schema_version
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def compute_cache_key(
        self,
        session_id: str,
        evidence_fingerprint: str,
        provider_id: str,
        model_id: str,
        model_version: str,
        config_hash: str = "default",
    ) -> str:
        """Compute deterministic SHA-256 fingerprint for semantic inference inputs."""
        components = [
            f"session:{session_id}",
            f"prov:{provider_id}",
            f"model:{model_id}:{model_version}",
            f"schema:{self.schema_version}",
            f"ev_fp:{evidence_fingerprint}",
            f"cfg:{config_hash}",
        ]
        raw_key = "|".join(components)
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def get(self, cache_key: str) -> Optional[DemonstrationUnderstanding]:
        """Retrieve cached demonstration understanding if present and valid."""
        cache_file = self.cache_dir / f"{cache_key}.json"
        if not cache_file.exists():
            return None

        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict) or "task_id" not in data:
                logger.warning(f"Corrupted cache file {cache_file}, discarding.")
                cache_file.unlink(missing_ok=True)
                return None

            understanding = DemonstrationUnderstanding.from_dict(data)
            return understanding
        except Exception as e:
            logger.warning(f"Failed to read cache file {cache_file}: {e}")
            cache_file.unlink(missing_ok=True)
            return None

    def put(self, cache_key: str, understanding: DemonstrationUnderstanding) -> None:
        """Store demonstration understanding in the cache atomically."""
        cache_file = self.cache_dir / f"{cache_key}.json"
        tmp_file = self.cache_dir / f"{cache_key}.tmp.{hashlib.md5(cache_key.encode()).hexdigest()[:8]}"

        try:
            data = understanding.to_dict()
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            tmp_file.replace(cache_file)
        except Exception as e:
            logger.warning(f"Failed to write cache entry {cache_key}: {e}")
            if tmp_file.exists():
                tmp_file.unlink(missing_ok=True)

    def clear(self) -> int:
        """Clear all cached entries."""
        count = 0
        for f in self.cache_dir.glob("*.json"):
            try:
                f.unlink()
                count += 1
            except Exception:
                pass
        return count
