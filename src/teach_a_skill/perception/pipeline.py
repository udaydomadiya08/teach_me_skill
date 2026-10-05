"""Perception pipeline coordinating frame validation, deduplication, OCR, UI detection, and fusion."""

import hashlib
import time
from pathlib import Path
from typing import Any, Callable, Optional, Union

import numpy as np
from PIL import Image

from teach_a_skill.core.logging import get_logger
from teach_a_skill.perception.cache import PerceptionCache
from teach_a_skill.perception.detection.base import UIElementDetector
from teach_a_skill.perception.detection.registry import get_ui_detector
from teach_a_skill.perception.fusion import PerceptionFusion
from teach_a_skill.perception.models import (
    OCRResult,
    PerceptionFrame,
    PerceptionManifest,
    PerceptionMode,
    TextRegion,
    UIElement,
)
from teach_a_skill.perception.ocr.base import OCRProvider
from teach_a_skill.perception.ocr.registry import get_ocr_provider
from teach_a_skill.perception.privacy import PerceptionPrivacyManager
from teach_a_skill.perception.reading_order import DeterministicReadingOrder
from teach_a_skill.perception.storage import PerceptionStorage
from teach_a_skill.storage.manager import StorageManager

logger = get_logger("teach_a_skill.perception.pipeline")


class PerceptionPipeline:
    """Orchestrates perception processing over demonstration screen checkpoint frames."""

    def __init__(
        self,
        storage_manager: StorageManager,
        ocr_provider: Optional[OCRProvider] = None,
        ui_detector: Optional[UIElementDetector] = None,
        use_accessibility: bool = False,
        enable_cache: bool = True,
        hardware_tier: str = "BASELINE",
        max_dimension: Optional[int] = None,
        dedup_threshold: float = 0.99,
        privacy_manager: Optional[PerceptionPrivacyManager] = None,
    ) -> None:
        self.storage_manager = storage_manager
        self.ocr_provider = ocr_provider or get_ocr_provider(hardware_tier=hardware_tier)
        self.ui_detector = ui_detector or get_ui_detector(use_accessibility=use_accessibility)
        self.use_accessibility = use_accessibility
        self.enable_cache = enable_cache
        self.hardware_tier = hardware_tier
        self.max_dimension = max_dimension
        self.dedup_threshold = dedup_threshold
        self.privacy_manager = privacy_manager or PerceptionPrivacyManager()

        self.cache = PerceptionCache(storage_manager.get_path("cache", "perception"))
        self.fusion = PerceptionFusion()

    def process_session(
        self,
        session_id: str,
        force_reprocess: bool = False,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        max_frames: Optional[int] = None,
    ) -> Path:
        """Run full perception pipeline over all frames in a demonstration session."""
        t_start = time.perf_counter()
        session_dir = self.storage_manager.get_path("recordings", session_id)
        if not session_dir.exists():
            raise FileNotFoundError(f"Recording session '{session_id}' not found.")

        frame_index_file = session_dir / "metadata" / "frame_index.json"
        if frame_index_file.exists():
            frame_data = self.storage_manager.read_metadata(frame_index_file)
            raw_frames = frame_data.get("frames", [])
        else:
            frames_dir = session_dir / "frames"
            if frames_dir.exists():
                raw_frames = [
                    {
                        "frame_id": p.stem,
                        "path": f"frames/{p.name}",
                        "filename": p.name,
                        "image_format": p.suffix.lstrip("."),
                    }
                    for p in sorted(frames_dir.glob("*.png"))
                ]
            else:
                raise FileNotFoundError(f"Neither frame index nor frames directory found in '{session_dir}'")

        if max_frames is not None and max_frames > 0:
            raw_frames = raw_frames[:max_frames]

        rep_storage = PerceptionStorage(self.storage_manager, session_id)
        staged_dir = rep_storage.create_temp_build_environment()

        config_hash = hashlib.sha256(
            f"{self.ocr_provider.provider_id}:{self.ocr_provider.provider_version}:"
            f"{self.ui_detector.detector_id}:{self.ui_detector.detector_version}:"
            f"{self.hardware_tier}:{self.max_dimension}".encode("utf-8")
        ).hexdigest()[:16]

        all_frames: list[PerceptionFrame] = []
        all_elements: list[UIElement] = []
        all_text_regions: list[TextRegion] = []
        all_ocr_results: list[OCRResult] = []
        source_checksums: dict[str, str] = {}

        # Spatial & temporal indexes
        indexes: dict[str, Any] = {
            "frame_to_element_ids": {},
            "frame_to_text_ids": {},
            "text_to_frame_ids": {},
            "element_type_index": {},
        }

        # Deduplication tracker: maps image hash to previous results
        last_frame_pixels: Optional[np.ndarray] = None
        last_processed_tuple: Optional[tuple[list[UIElement], list[TextRegion], OCRResult]] = None

        total_frames = len(raw_frames)
        cache_hit_count = 0

        for f_idx, rf in enumerate(raw_frames):
            frame_id = rf.get("frame_id", f"frame_{f_idx:05d}")
            rel_path = rf.get("path") or rf.get("filename") or f"frames/{frame_id}.{rf.get('image_format', 'png')}"
            frame_path = session_dir / rel_path

            if not frame_path.exists():
                logger.warning(f"Frame file not found: {frame_path}")
                continue

            frame_bytes = frame_path.read_bytes()
            frame_checksum = rf.get("checksum") or hashlib.sha256(frame_bytes).hexdigest()
            source_checksums[frame_id] = frame_checksum

            t_frame_start = time.perf_counter()
            cache_key = self.cache.compute_cache_key(
                frame_checksum=frame_checksum,
                provider_id=self.ocr_provider.provider_id,
                provider_version=self.ocr_provider.provider_version,
                detector_id=self.ui_detector.detector_id,
                config_hash=config_hash,
            )

            cached_data = self.cache.get(cache_key) if (self.enable_cache and not force_reprocess) else None
            is_cache_hit = cached_data is not None

            if is_cache_hit and cached_data:
                cache_hit_count += 1
                p_frame = PerceptionFrame.from_dict(cached_data["perception_frame"])
                p_frame.cache_hit = True
                elements = [UIElement.from_dict(e) for e in cached_data["elements"]]
                text_regions = [TextRegion.from_dict(t) for t in cached_data["text_regions"]]
                ocr_result = OCRResult.from_dict(cached_data["ocr_result"])
            else:
                # Perceptual deduplication check
                is_duplicate = False
                curr_pil = Image.open(frame_path)
                curr_w, curr_h = curr_pil.size
                curr_pixels = np.array(curr_pil.convert("L").resize((64, 64)))

                if last_frame_pixels is not None and last_processed_tuple is not None:
                    diff = np.mean(np.abs(curr_pixels - last_frame_pixels)) / 255.0
                    similarity = 1.0 - diff
                    if similarity >= self.dedup_threshold:
                        is_duplicate = True

                if is_duplicate and last_processed_tuple is not None:
                    base_elems, base_texts, base_ocr = last_processed_tuple
                    # Deep-copy and re-tag for current frame
                    text_regions = [
                        TextRegion(
                            region_id=f"{t.region_id}_dup_{frame_id}",
                            frame_id=frame_id,
                            text=t.text,
                            raw_text=t.raw_text,
                            normalized_text=t.normalized_text,
                            bbox=t.bbox,
                            confidence=t.confidence,
                            language=t.language,
                            line_id=t.line_id,
                            word_ids=list(t.word_ids),
                            reading_order=t.reading_order,
                            source_provider=t.source_provider,
                            provenance={"deduplicated_from": base_ocr.frame_id},
                        )
                        for t in base_texts
                    ]
                    elements = [
                        UIElement(
                            element_id=f"{e.element_id}_dup_{frame_id}",
                            frame_id=frame_id,
                            element_type=e.element_type,
                            bbox=e.bbox,
                            confidence=e.confidence,
                            sources=list(e.sources),
                            text_content=e.text_content,
                            accessibility_attributes=dict(e.accessibility_attributes),
                            reading_order=e.reading_order,
                            provenance={"deduplicated_from": base_ocr.frame_id},
                        )
                        for e in base_elems
                    ]
                    ocr_result = OCRResult(
                        ocr_id=f"ocr_dup_{frame_id}",
                        frame_id=frame_id,
                        provider_id=self.ocr_provider.provider_id,
                        provider_version=self.ocr_provider.provider_version,
                        text_regions=text_regions,
                        raw_full_text=base_ocr.raw_full_text,
                        confidence_aggregate=base_ocr.confidence_aggregate,
                        timing_ms=0.5,
                        provenance={"deduplicated_from": base_ocr.frame_id},
                    )
                else:
                    # Full perception processing
                    frame_meta = {
                        "width": curr_w,
                        "height": curr_h,
                        "scale_factor": float(rf.get("scale_factor", 1.0)),
                        "display_id": rf.get("display_id"),
                    }

                    # 1. OCR text detection
                    ocr_result = self.ocr_provider.detect_text(frame_path, frame_id=frame_id)

                    # Privacy text sanitization
                    for tr in ocr_result.text_regions:
                        tr.text = self.privacy_manager.sanitize_text(tr.text)
                        tr.normalized_text = self.privacy_manager.sanitize_text(tr.normalized_text)

                    # 2. UI element detection
                    geom_elements = self.ui_detector.detect_elements(
                        frame_path,
                        frame_id=frame_id,
                        frame_metadata=frame_meta,
                        text_regions=ocr_result.text_regions,
                    )

                    # 3. Optional accessibility elements
                    ax_elements: list[UIElement] = []
                    if self.use_accessibility:
                        try:
                            from teach_a_skill.perception.detection.accessibility import PlatformAccessibilityDetector

                            ax_det = PlatformAccessibilityDetector()
                            if ax_det.is_available():
                                ax_elements = ax_det.detect_elements(
                                    frame_path, frame_id=frame_id, frame_metadata=frame_meta
                                )
                        except Exception:
                            pass

                    # 4. Multi-source fusion
                    elements = self.fusion.fuse(
                        geometric_elements=geom_elements,
                        accessibility_elements=ax_elements,
                        text_regions=ocr_result.text_regions,
                        frame_id=frame_id,
                    )
                    text_regions = ocr_result.text_regions

                    last_frame_pixels = curr_pixels
                    last_processed_tuple = (elements, text_regions, ocr_result)

                # Store into cache
                frame_dur_ms = (time.perf_counter() - t_frame_start) * 1000.0
                p_frame = PerceptionFrame(
                    perception_frame_id=f"perc_{frame_id}",
                    frame_id=frame_id,
                    session_id=session_id,
                    timestamp_ns=int(rf.get("timestamp_ns", 0)),
                    relative_time_ms=round(float(rf.get("monotonic_timestamp", 0.0)) * 1000.0, 2),
                    frame_path=rel_path,
                    frame_checksum=frame_checksum,
                    frame_width=curr_w,
                    frame_height=curr_h,
                    scale_factor=float(rf.get("scale_factor", 1.0)),
                    mode=(
                        PerceptionMode.SCREEN_AND_ACCESSIBILITY.value
                        if self.use_accessibility
                        else PerceptionMode.SCREEN_ONLY.value
                    ),
                    elements_count=len(elements),
                    text_regions_count=len(text_regions),
                    processing_time_ms=round(frame_dur_ms, 2),
                    cache_hit=is_cache_hit,
                    config_hash=config_hash,
                )
                if self.enable_cache and not is_cache_hit:
                    self.cache.put(cache_key, p_frame, elements, text_regions, ocr_result)

            all_frames.append(p_frame)
            all_elements.extend(elements)
            all_text_regions.extend(text_regions)
            all_ocr_results.append(ocr_result)

            # Build spatial indexes
            indexes["frame_to_element_ids"][frame_id] = [e.element_id for e in elements]
            indexes["frame_to_text_ids"][frame_id] = [t.region_id for t in text_regions]
            for t in text_regions:
                clean_word = t.text.lower()
                indexes["text_to_frame_ids"].setdefault(clean_word, []).append(frame_id)
            for e in elements:
                t_str = e.element_type.value if hasattr(e.element_type, "value") else str(e.element_type)
                indexes["element_type_index"].setdefault(t_str, []).append(e.element_id)

            if progress_callback:
                progress_callback(f_idx + 1, total_frames)

        total_duration = time.perf_counter() - t_start

        # Build manifest
        manifest = PerceptionManifest(
            perception_id=f"perc_man_{session_id}",
            session_id=session_id,
            schema_version="1.0.0",
            derivation_version="phase5-v1",
            config_hash=config_hash,
            ocr_provider=self.ocr_provider.provider_id,
            detector_provider=self.ui_detector.detector_id,
            mode=(
                PerceptionMode.SCREEN_AND_ACCESSIBILITY.value
                if self.use_accessibility
                else PerceptionMode.SCREEN_ONLY.value
            ),
            total_frames_processed=len(all_frames),
            total_elements=len(all_elements),
            total_text_regions=len(all_text_regions),
            cache_hit_count=cache_hit_count,
            processing_duration_sec=round(total_duration, 3),
            source_frame_checksums=source_checksums,
            metadata={"hardware_tier": self.hardware_tier},
        )

        # Stage and atomically promote
        final_dir = rep_storage.write_staged_perception(
            staged_dir=staged_dir,
            manifest=manifest,
            frames=all_frames,
            elements=all_elements,
            text_regions=all_text_regions,
            ocr_results=all_ocr_results,
            indexes=indexes,
        )
        logger.info(
            f"Perception partition built for session '{session_id}' "
            f"({len(all_frames)} frames, {len(all_elements)} elements, {len(all_text_regions)} text regions) in {total_duration:.2f}s."
        )
        return final_dir
