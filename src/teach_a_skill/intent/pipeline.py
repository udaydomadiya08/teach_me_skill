"""End-to-end pipeline coordinating semantic intent inference, task segmentation, graph construction, and storage."""

import hashlib
import time
from pathlib import Path
from typing import Any, Optional

from teach_a_skill.core.logging import get_logger
from teach_a_skill.hardware.tiers import HardwareTier
from teach_a_skill.intent.cache import IntentCache
from teach_a_skill.intent.graph import TaskGraph
from teach_a_skill.intent.models import (
    DemonstrationUnderstanding,
    IntentManifest,
)
from teach_a_skill.intent.providers.base import SemanticProvider
from teach_a_skill.intent.providers.registry import SemanticProviderRegistry
from teach_a_skill.intent.storage import IntentStorage
from teach_a_skill.multimodal.storage import MultimodalStorage
from teach_a_skill.perception.storage import PerceptionStorage
from teach_a_skill.representation.storage import RepresentationStorage
from teach_a_skill.storage.manager import StorageManager
from teach_a_skill.teaching.storage import TeachingStorage

logger = get_logger("teach_a_skill.intent.pipeline")


class IntentPipeline:
    """Coordinates evidence aggregation from Phases 3-6, semantic provider inference, caching, and atomic persistence."""

    def __init__(
        self,
        storage_manager: StorageManager,
        provider: Optional[SemanticProvider] = None,
        provider_name: Optional[str] = None,
        cache_enabled: bool = True,
        hardware_tier: Optional[HardwareTier] = None,
    ) -> None:
        self.storage_manager = storage_manager
        self.registry = SemanticProviderRegistry(hardware_tier=hardware_tier)
        if provider:
            self.provider = provider
        else:
            self.provider = self.registry.select_best_provider(preferred_provider=provider_name)

        cache_dir = storage_manager.get_path("cache", "intent")
        self.cache = IntentCache(cache_dir=cache_dir) if cache_enabled else None

    def process_session(
        self,
        session_id: str,
        force_rebuild: bool = False,
    ) -> tuple[DemonstrationUnderstanding, IntentManifest]:
        """Infer and persist semantic demonstration understanding for a given session."""
        storage = IntentStorage(self.storage_manager, session_id)
        if not force_rebuild and storage.exists():
            manifest = storage.read_manifest()
            tasks = storage.read_tasks()
            if manifest and tasks:
                logger.info(f"Phase 7 intent artifacts already exist for session '{session_id}'. Reusing existing.")
                return tasks[0], manifest

        start_time = time.perf_counter()
        logger.info(
            f"Analyzing demonstration intent for session '{session_id}' using provider '{self.provider.capabilities.provider_id}'..."
        )

        # 1. Gather Phase 6 Multimodal Observations
        mm_storage = MultimodalStorage(self.storage_manager, session_id)
        observations = mm_storage.read_observations() if mm_storage.exists() else []

        # 2. Gather Phase 4 Canonical Events
        rep_storage = RepresentationStorage(self.storage_manager, session_id)
        canonical_events = list(rep_storage.stream_canonical_events()) if rep_storage.exists() else []

        # 3. Gather Phase 5 Perception
        perc_storage = PerceptionStorage(self.storage_manager, session_id)
        text_regions = list(perc_storage.stream_text_regions()) if perc_storage.exists() else []
        ui_elements = list(perc_storage.stream_elements()) if perc_storage.exists() else []

        # 4. Gather Phase 3 Speech transcripts and Annotations
        transcripts = []
        annotations = []
        try:
            t_storage = TeachingStorage(self.storage_manager, session_id)
            transcripts = t_storage.read_transcript_segments()
            annotations = t_storage.read_annotations()
        except Exception as e:
            logger.debug(f"Teaching evidence unreadable or empty: {e}")

        context_data: dict[str, Any] = {
            "canonical_events": canonical_events,
            "transcripts": transcripts,
            "annotations": annotations,
            "text_regions": text_regions,
            "ui_elements": ui_elements,
        }

        # 5. Compute evidence fingerprint for cache & provenance verification
        fp_components = [
            f"obs:{len(observations)}",
            f"events:{len(canonical_events)}",
            f"transcripts:{len(transcripts)}",
            f"annotations:{len(annotations)}",
            f"texts:{len(text_regions)}",
            f"uis:{len(ui_elements)}",
        ]
        if observations:
            fp_components.append(f"first_obs:{observations[0].observation_id}")
            fp_components.append(f"last_obs:{observations[-1].observation_id}")
        evidence_fingerprint = hashlib.sha256("|".join(fp_components).encode("utf-8")).hexdigest()

        # 6. Check content-addressed cache
        cache_key = None
        understanding: Optional[DemonstrationUnderstanding] = None
        if self.cache:
            cache_key = self.cache.compute_cache_key(
                session_id=session_id,
                evidence_fingerprint=evidence_fingerprint,
                provider_id=self.provider.capabilities.provider_id,
                model_id=self.provider.capabilities.model_id,
                model_version=self.provider.capabilities.model_version,
            )
            understanding = self.cache.get(cache_key)

        # 7. Execute semantic inference if cache miss
        if understanding is None:
            understanding = self.provider.infer(
                session_id=session_id,
                observations=observations,
                context_data=context_data,
            )
            # Build and attach task graph representation
            graph = TaskGraph.build_from_understanding(understanding)
            understanding.metadata["task_graph"] = graph.to_dict()
            understanding.metadata["evidence_fingerprint"] = evidence_fingerprint

            if self.cache and cache_key:
                self.cache.put(cache_key, understanding)

        duration = time.perf_counter() - start_time

        # 8. Build manifest
        manifest = IntentManifest(
            manifest_id=f"manifest_intent_{session_id}",
            session_id=session_id,
            schema_version="1.0.0",
            derivation_version="phase7-v1",
            provider_id=self.provider.capabilities.provider_id,
            model_id=self.provider.capabilities.model_id,
            total_stages=len(understanding.stages),
            total_actions=len(understanding.actions),
            total_entities=len(understanding.entities),
            total_ambiguities=len(understanding.ambiguities),
            primary_intent_type=str(understanding.primary_intent.intent_type) if understanding.primary_intent else None,
            overall_confidence=understanding.confidence,
            processing_duration_sec=round(duration, 4),
            metadata={
                "evidence_fingerprint": evidence_fingerprint,
                "hardware_tier": str(self.registry.hardware_tier),
            },
        )

        # 9. Atomically persist artifacts
        storage.write_intent_artifacts(understanding=understanding, manifest=manifest)
        logger.info(f"Phase 7 intent analysis completed for session '{session_id}' in {duration:.3f}s")

        return understanding, manifest
