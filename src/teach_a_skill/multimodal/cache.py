"""Content-addressed multimodal inference cache."""

import hashlib
import json
from pathlib import Path
from typing import Any, Optional

from teach_a_skill.core.logging import get_logger
from teach_a_skill.multimodal.context import MultimodalContext
from teach_a_skill.multimodal.models import MultimodalObservation

logger = get_logger("teach_a_skill.multimodal.cache")


class MultimodalCache:
    """Content-addressed cache for multimodal inference and grounding results."""

    def __init__(
        self,
        cache_dir: Path,
        max_entries: int = 1000,
        preprocessing_version: str = "phase6-v1",
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.max_entries = max_entries
        self.preprocessing_version = preprocessing_version
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def compute_cache_key(
        self,
        context: MultimodalContext,
        provider_id: str,
        model_id: str,
        model_version: str,
        config_hash: str = "default",
    ) -> str:
        """Compute deterministic SHA-256 fingerprint from all context inputs and model specs."""
        w = context.window
        components = [
            f"prov:{provider_id}",
            f"model:{model_id}:{model_version}",
            f"prep:{self.preprocessing_version}",
            f"cfg:{config_hash}",
            f"win:{w.window_id}:{w.start_timestamp_ns}:{w.end_timestamp_ns}",
            f"frame:{context.primary_frame_id or 'none'}",
            f"ptr:{context.pointer_position}",
            f"app:{w.active_application}:{w.active_window_title}",
            f"ocr:{','.join(sorted(tr.region_id for tr in context.text_regions))}",
            f"ui:{','.join(sorted(el.element_id for el in context.ui_elements))}",
            f"spk:{','.join(sorted(seg.segment_id for seg in context.transcripts))}",
            f"ann:{','.join(sorted(ann.annotation_id for ann in context.annotations))}",
        ]
        raw_key = "|".join(components)
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def get(self, cache_key: str) -> Optional[list[MultimodalObservation]]:
        """Retrieve cached multimodal observations if present and valid."""
        cache_file = self.cache_dir / f"{cache_key}.json"
        if not cache_file.exists():
            return None

        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, list):
                logger.warning(f"Corrupted cache file {cache_file} (not a list), discarding.")
                cache_file.unlink(missing_ok=True)
                return None

            observations = [MultimodalObservation.from_dict(item) for item in data]
            return observations
        except Exception as e:
            logger.warning(f"Failed to read cache file {cache_file}: {e}")
            cache_file.unlink(missing_ok=True)
            return None

    def put(self, cache_key: str, observations: list[MultimodalObservation]) -> None:
        """Store multimodal observations in the cache atomically."""
        cache_file = self.cache_dir / f"{cache_key}.json"
        tmp_file = self.cache_dir / f"{cache_key}.tmp.{hashlib.md5(cache_key.encode()).hexdigest()[:8]}"

        try:
            data = [obs.to_dict() for obs in observations]
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
