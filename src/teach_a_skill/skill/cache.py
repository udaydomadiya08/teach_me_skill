"""Content-addressed compilation cache for Skill IR."""

import hashlib
import json
from pathlib import Path
from typing import Optional

from teach_a_skill.core.logging import get_logger
from teach_a_skill.skill.models import SkillIR

logger = get_logger("teach_a_skill.skill.cache")


class SkillCache:
    """Content-addressed cache for compiled Skill Intermediate Representations."""

    def __init__(
        self,
        cache_dir: Path,
        schema_version: str = "1.0.0",
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.schema_version = schema_version
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def compute_cache_key(
        self,
        session_id: str,
        semantic_fingerprint: str,
        compiler_id: str,
        compiler_version: str,
        config_hash: str = "default",
    ) -> str:
        """Compute deterministic SHA-256 fingerprint for compilation inputs."""
        components = [
            f"session:{session_id}",
            f"sem_fp:{semantic_fingerprint}",
            f"compiler:{compiler_id}:{compiler_version}",
            f"schema:{self.schema_version}",
            f"cfg:{config_hash}",
        ]
        raw_key = "|".join(components)
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def get(self, cache_key: str) -> Optional[SkillIR]:
        """Retrieve cached SkillIR if present and valid."""
        cache_file = self.cache_dir / f"{cache_key}.json"
        if not cache_file.exists():
            return None

        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict) or "skill_id" not in data:
                cache_file.unlink(missing_ok=True)
                return None

            return SkillIR.from_dict(data)
        except Exception as e:
            logger.warning(f"Failed to read skill cache file {cache_file}: {e}")
            cache_file.unlink(missing_ok=True)
            return None

    def put(self, cache_key: str, skill: SkillIR) -> None:
        """Store compiled SkillIR in cache atomically."""
        cache_file = self.cache_dir / f"{cache_key}.json"
        tmp_file = self.cache_dir / f"{cache_key}.tmp.{hashlib.md5(cache_key.encode()).hexdigest()[:8]}"

        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(skill.to_dict(), f, indent=2)
            tmp_file.replace(cache_file)
        except Exception as e:
            logger.warning(f"Failed to write skill cache entry {cache_key}: {e}")
            if tmp_file.exists():
                tmp_file.unlink(missing_ok=True)

    def clear(self) -> int:
        """Clear all cached compilation entries."""
        count = 0
        for f in self.cache_dir.glob("*.json"):
            try:
                f.unlink()
                count += 1
            except Exception:
                pass
        return count
