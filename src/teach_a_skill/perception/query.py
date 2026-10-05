"""Query API and spatial retrieval engine for Phase 5 perception artifacts."""

import bisect
from typing import Any, Optional, Union

from teach_a_skill.core.errors import StorageError
from teach_a_skill.perception.models import (
    BoundingBox,
    OCRResult,
    PerceptionFrame,
    PerceptionManifest,
    TextRegion,
    UIElement,
    UIElementType,
)
from teach_a_skill.perception.storage import PerceptionStorage
from teach_a_skill.storage.manager import StorageManager


class PerceptionQueryEngine:
    """Local, structured query engine operating over on-disk perception partitions."""

    def __init__(self, storage_manager: StorageManager, session_id: str) -> None:
        self.storage_manager = storage_manager
        self.session_id = session_id
        self.storage = PerceptionStorage(storage_manager, session_id)

        if not self.storage.exists():
            raise StorageError(
                f"Perception partition for session '{session_id}' not found. "
                "Run 'teach-skill perception process' first."
            )

        # Lazy caches
        self._manifest: Optional[PerceptionManifest] = None
        self._indexes: Optional[dict[str, Any]] = None
        self._frames_cache: Optional[dict[str, PerceptionFrame]] = None
        self._elements_cache: Optional[dict[str, UIElement]] = None
        self._frame_elements_cache: Optional[dict[str, list[UIElement]]] = None
        self._frame_texts_cache: Optional[dict[str, list[TextRegion]]] = None
        self._ocr_cache: Optional[dict[str, OCRResult]] = None
        self._time_to_frame: Optional[list[tuple[int, str]]] = None

    @property
    def manifest(self) -> PerceptionManifest:
        if self._manifest is None:
            self._manifest = self.storage.read_manifest()
        return self._manifest

    def _ensure_indexes(self) -> dict[str, Any]:
        if self._indexes is None:
            self._indexes = self.storage.read_indexes()
        return self._indexes

    def _ensure_frames(self) -> dict[str, PerceptionFrame]:
        if self._frames_cache is None:
            self._frames_cache = {f.frame_id: f for f in self.storage.stream_frames()}
            # Precompute sorted timestamp mapping for temporal queries
            self._time_to_frame = sorted(
                [(f.timestamp_ns, f.frame_id) for f in self._frames_cache.values()],
                key=lambda x: x[0],
            )
        return self._frames_cache

    def _ensure_elements(self) -> dict[str, UIElement]:
        if self._elements_cache is None:
            self._elements_cache = {}
            self._frame_elements_cache = {}
            for el in self.storage.stream_elements():
                self._elements_cache[el.element_id] = el
                self._frame_elements_cache.setdefault(el.frame_id, []).append(el)
        return self._elements_cache

    def _ensure_texts(self) -> dict[str, list[TextRegion]]:
        if self._frame_texts_cache is None:
            self._frame_texts_cache = {}
            for tr in self.storage.stream_text_regions():
                self._frame_texts_cache.setdefault(tr.frame_id, []).append(tr)
        return self._frame_texts_cache

    def _ensure_ocr(self) -> dict[str, OCRResult]:
        if self._ocr_cache is None:
            self._ocr_cache = {ocr.frame_id: ocr for ocr in self.storage.stream_ocr_results()}
        return self._ocr_cache

    # 1. Primary frame perception queries
    def get_perception_frame(self, frame_id: str) -> Optional[PerceptionFrame]:
        """Retrieve perception checkpoint metadata for a frame."""
        frames = self._ensure_frames()
        return frames.get(frame_id)

    def get_ui_elements(self, frame_id: str) -> list[UIElement]:
        """Return all detected UI elements for a frame ordered by reading order."""
        self._ensure_elements()
        return list(self._frame_elements_cache.get(frame_id, [])) if self._frame_elements_cache else []

    def get_text_regions(self, frame_id: str) -> list[TextRegion]:
        """Return all OCR text regions detected in a frame."""
        texts = self._ensure_texts()
        return list(texts.get(frame_id, []))

    def get_ocr(self, frame_id: str) -> Optional[OCRResult]:
        """Return raw OCR result for a frame."""
        ocr_map = self._ensure_ocr()
        return ocr_map.get(frame_id)

    def get_element(self, element_id: str) -> Optional[UIElement]:
        """Look up UI element by element_id."""
        elems = self._ensure_elements()
        return elems.get(element_id)

    # 2. Spatial queries
    def get_text_at(self, x: float, y: float, frame_id: str, normalized: bool = False) -> Optional[TextRegion]:
        """Find the text region containing the coordinate (x, y)."""
        text_regions = self.get_text_regions(frame_id)
        for tr in text_regions:
            if tr.bbox.contains(x, y, normalized=normalized):
                return tr
        return None

    def get_nearest_text(
        self,
        frame_id: str,
        x: float,
        y: float,
        normalized: bool = False,
    ) -> Optional[TextRegion]:
        """Find the closest text region to a given coordinate."""
        text_regions = self.get_text_regions(frame_id)
        if not text_regions:
            return None

        best_region: Optional[TextRegion] = None
        min_dist_sq = float("inf")

        for tr in text_regions:
            if normalized:
                cx = tr.bbox.normalized_x + (tr.bbox.normalized_width / 2.0)
                cy = tr.bbox.normalized_y + (tr.bbox.normalized_height / 2.0)
            else:
                cx = tr.bbox.x + (tr.bbox.width / 2.0)
                cy = tr.bbox.y + (tr.bbox.height / 2.0)

            dist_sq = (cx - x) ** 2 + (cy - y) ** 2
            if dist_sq < min_dist_sq:
                min_dist_sq = dist_sq
                best_region = tr

        return best_region

    def get_elements_in_region(self, frame_id: str, region_bbox: BoundingBox) -> list[UIElement]:
        """Find all UI elements overlapping or contained inside a bounding box region."""
        elements = self.get_ui_elements(frame_id)
        matching: list[UIElement] = []
        for el in elements:
            if el.bbox.intersection_over_union(region_bbox) > 0.0 or region_bbox.contains(
                el.bbox.normalized_x, el.bbox.normalized_y, normalized=True
            ):
                matching.append(el)
        return matching

    def get_visible_text(self, frame_id: str) -> str:
        """Return all text visibly present in the frame in reading order."""
        texts = self.get_text_regions(frame_id)
        texts.sort(key=lambda t: t.reading_order)
        return "\n".join(t.text for t in texts)

    def get_elements_by_type(
        self,
        frame_id: str,
        element_type: Union[UIElementType, str],
    ) -> list[UIElement]:
        """Filter elements in a frame by UI element type."""
        target_type = element_type.value if hasattr(element_type, "value") else str(element_type)
        elements = self.get_ui_elements(frame_id)
        return [
            e for e in elements
            if (e.element_type.value if hasattr(e.element_type, "value") else str(e.element_type)) == target_type
        ]

    # 3. Temporal query
    def get_perception_context(self, timestamp_ns: int) -> Optional[PerceptionFrame]:
        """Return the perception frame temporally closest to the requested timestamp."""
        self._ensure_frames()
        if not self._time_to_frame:
            return None

        # Binary search for closest timestamp
        times = [t[0] for t in self._time_to_frame]
        idx = bisect.bisect_left(times, timestamp_ns)

        if idx == 0:
            best_fid = self._time_to_frame[0][1]
        elif idx >= len(times):
            best_fid = self._time_to_frame[-1][1]
        else:
            d_before = abs(times[idx - 1] - timestamp_ns)
            d_after = abs(times[idx] - timestamp_ns)
            best_fid = self._time_to_frame[idx - 1][1] if d_before <= d_after else self._time_to_frame[idx][1]

        return self.get_perception_frame(best_fid)
