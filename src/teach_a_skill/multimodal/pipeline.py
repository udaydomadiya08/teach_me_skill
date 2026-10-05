"""Multimodal intelligence pipeline coordinating context, providers, fusion, and storage."""

import time
from pathlib import Path
from typing import Any, Optional

from teach_a_skill.core.logging import get_logger
from teach_a_skill.hardware.tiers import HardwareTier
from teach_a_skill.multimodal.cache import MultimodalCache
from teach_a_skill.multimodal.context import MultimodalContextBuilder
from teach_a_skill.multimodal.fusion import MultimodalFusionEngine
from teach_a_skill.multimodal.grounding import MultimodalGroundingEngine
from teach_a_skill.multimodal.models import (
    MultimodalManifest,
    MultimodalObservation,
    TemporalWindow,
)
from teach_a_skill.multimodal.providers.base import LocalMultimodalProvider
from teach_a_skill.multimodal.providers.registry import MultimodalProviderRegistry
from teach_a_skill.multimodal.storage import MultimodalStorage
from teach_a_skill.storage.manager import StorageManager

logger = get_logger("teach_a_skill.multimodal.pipeline")


class MultimodalPipeline:
    """End-to-end pipeline deriving structured multimodal observations from Phase 2-5 evidence."""

    def __init__(
        self,
        storage_manager: StorageManager,
        provider: Optional[LocalMultimodalProvider] = None,
        provider_name: Optional[str] = None,
        cache_enabled: bool = True,
        hardware_tier: Optional[HardwareTier] = None,
        max_context_elements: int = 50,
    ) -> None:
        self.storage_manager = storage_manager
        self.registry = MultimodalProviderRegistry(hardware_tier=hardware_tier)
        if provider:
            self.provider = provider
        else:
            self.provider = self.registry.select_best_provider(preferred_provider=provider_name)

        self.context_builder = MultimodalContextBuilder(
            storage_manager=storage_manager,
            max_context_elements=max_context_elements,
        )
        self.grounding_engine = MultimodalGroundingEngine()
        self.fusion_engine = MultimodalFusionEngine(grounding_engine=self.grounding_engine)

        cache_dir = storage_manager.get_path("cache", "multimodal")
        self.cache = MultimodalCache(cache_dir=cache_dir) if cache_enabled else None

    def process_session(
        self,
        session_id: str,
        force_rebuild: bool = False,
        max_windows: Optional[int] = None,
    ) -> MultimodalManifest:
        """Process a session and persist multimodal intelligence artifacts."""
        storage = MultimodalStorage(self.storage_manager, session_id)
        if not force_rebuild and storage.exists():
            existing_manifest = storage.read_manifest()
            if existing_manifest:
                logger.info(
                    f"Multimodal artifacts already exist for session '{session_id}'. Reusing existing."
                )
                return existing_manifest

        start_time = time.perf_counter()
        logger.info(
            f"Processing session '{session_id}' using provider '{self.provider.capabilities.provider_id}'..."
        )

        # 1. Build bounded temporal contexts from canonical events, perception, and transcripts
        contexts = self.context_builder.build_contexts_for_session(
            session_id=session_id,
            max_windows=max_windows,
        )

        windows: list[TemporalWindow] = []
        all_observations: list[MultimodalObservation] = []
        cache_hits = 0

        # 2. Incremental window-by-window processing to guarantee bounded memory
        for ctx in contexts:
            windows.append(ctx.window)
            window_obs: list[MultimodalObservation] = []

            # Check cache
            cache_key = None
            if self.cache:
                cache_key = self.cache.compute_cache_key(
                    context=ctx,
                    provider_id=self.provider.capabilities.provider_id,
                    model_id=self.provider.capabilities.model_id,
                    model_version=self.provider.capabilities.model_version,
                )
                cached = self.cache.get(cache_key)
                if cached is not None:
                    window_obs = cached
                    cache_hits += 1

            if not window_obs:
                # Provider inference
                provider_out = []
                try:
                    provider_out = self.provider.analyze(ctx)
                except Exception as e:
                    logger.warning(
                        f"Provider {self.provider.capabilities.provider_id} failed on window {ctx.window.window_id}: {e}. Falling back to deterministic grounding."
                    )

                # Fuse provider interpretation with deterministic grounding and hallucination checks
                window_obs = self.fusion_engine.fuse(ctx, provider_out)

                if self.cache and cache_key:
                    self.cache.put(cache_key, window_obs)

            all_observations.extend(window_obs)

        duration_sec = time.perf_counter() - start_time

        # 3. Create manifest
        caps = self.provider.capabilities
        manifest = MultimodalManifest(
            manifest_id=f"mm_manifest_{session_id}_{int(time.time())}",
            session_id=session_id,
            schema_version="1.0.0",
            derivation_version="phase6-v1",
            provider_id=caps.provider_id,
            model_id=caps.model_id,
            total_windows=len(windows),
            total_observations=len(all_observations),
            cache_hit_count=cache_hits,
            processing_duration_sec=round(duration_sec, 4),
            metadata={
                "hardware_tier": str(self.registry.hardware_tier),
                "is_mock": caps.category.value == "MOCK_PROVIDER",
                "is_deterministic": caps.category.value == "DETERMINISTIC_PROVIDER",
            },
        )

        # 4. Atomic persistence
        storage.write_multimodal_artifacts(
            windows=windows,
            observations=all_observations,
            manifest=manifest,
        )

        logger.info(
            f"Successfully processed session '{session_id}': {len(windows)} windows, {len(all_observations)} observations in {duration_sec:.2f}s."
        )
        return manifest
