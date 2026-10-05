"""Deterministic on-disk perception caching and invalidation engine."""

import hashlib
import json
from pathlib import Path
from typing import Any, Optional, Union

from teach_a_skill.core.logging import get_logger
from teach_a_skill.perception.models import OCRResult, PerceptionFrame, TextRegion, UIElement

logger = get_logger("teach_a_skill.perception.cache")


class PerceptionCache:
    """Manages cached perception frame results keyed by content checksum and configuration hash."""

    def __init__(self, cache_dir: Union[Path, str, Any]) -> None:
        if hasattr(cache_dir, "get_path"):
            self.cache_dir = cache_dir.get_path("cache", "perception")
        else:
            self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.hits = 0
        self.misses = 0

    def compute_cache_key(
        self,
        frame_checksum: str,
        provider_id: str,
        provider_version: str,
        detector_id: str,
        config_hash: str,
    ) -> str:
        """Calculate deterministic SHA-256 cache key."""
        payload = f"{frame_checksum}:{provider_id}:{provider_version}:{detector_id}:{config_hash}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(self, cache_key: str) -> Optional[dict[str, Any]]:
        """Retrieve cached perception frame data if present."""
        cache_file = self.cache_dir / f"{cache_key}.json"
        if not cache_file.exists():
            self.misses += 1
            return None

        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.hits += 1
            return data
        except Exception as e:
            logger.warning(f"Error reading perception cache file '{cache_file}': {e}")
            self.misses += 1
            return None

    def put(
        self,
        cache_key: str,
        perception_frame: PerceptionFrame,
        elements: list[UIElement],
        text_regions: list[TextRegion],
        ocr_result: OCRResult,
    ) -> None:
        """Store perception results under deterministic cache key."""
        cache_file = self.cache_dir / f"{cache_key}.json"
        payload = {
            "cache_key": cache_key,
            "perception_frame": perception_frame.to_dict(),
            "elements": [e.to_dict() for e in elements],
            "text_regions": [t.to_dict() for t in text_regions],
            "ocr_result": ocr_result.to_dict(),
        }
        temp_file = cache_file.with_suffix(".tmp")
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, separators=(",", ":"))
            temp_file.replace(cache_file)
        except Exception as e:
            logger.warning(f"Failed to write perception cache for key {cache_key}: {e}")
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass

    def invalidate(self, cache_key: str) -> bool:
        """Invalidate a specific cache entry."""
        cache_file = self.cache_dir / f"{cache_key}.json"
        if cache_file.exists():
            try:
                cache_file.unlink()
                return True
            except Exception:
                pass
        return False

    def clear(self) -> int:
        """Clear all cached entries."""
        count = 0
        for p in self.cache_dir.glob("*.json"):
            try:
                p.unlink()
                count += 1
            except Exception:
                pass
        return count
