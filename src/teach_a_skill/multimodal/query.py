"""Query interface for structured multimodal observations."""

from typing import Any, Optional

from teach_a_skill.multimodal.models import (
    MultimodalEvidenceRef,
    MultimodalObservation,
    ObservationType,
    TemporalWindow,
)
from teach_a_skill.multimodal.storage import MultimodalStorage
from teach_a_skill.storage.manager import StorageManager


class MultimodalQueryEngine:
    """Provides querying across structured multimodal observations."""

    def __init__(self, storage_manager: StorageManager, session_id: str) -> None:
        self.storage = MultimodalStorage(storage_manager, session_id)
        self.session_id = session_id
        self._observations: Optional[list[MultimodalObservation]] = None
        self._windows: Optional[list[TemporalWindow]] = None

    def _ensure_loaded(self) -> None:
        if self._observations is None:
            self._observations = self.storage.read_observations()
        if self._windows is None:
            self._windows = self.storage.read_windows()

    def get_all_observations(self) -> list[MultimodalObservation]:
        """Return all multimodal observations for the session."""
        self._ensure_loaded()
        return list(self._observations or [])

    def get_observations_by_type(self, obs_type: ObservationType) -> list[MultimodalObservation]:
        """Filter observations by observation type."""
        self._ensure_loaded()
        return [o for o in (self._observations or []) if o.observation_type == obs_type]

    def get_pointer_interactions(self) -> list[MultimodalObservation]:
        """Retrieve observations where a pointer co-occurred near UI or OCR regions."""
        self._ensure_loaded()
        target_types = {
            ObservationType.POINTER_CLICK_TARGET,
            ObservationType.POINTER_PROXIMITY,
        }
        return [o for o in (self._observations or []) if o.observation_type in target_types]

    def get_spoken_associations(self) -> list[MultimodalObservation]:
        """Retrieve observations linking spoken utterances to timeline or visible text."""
        self._ensure_loaded()
        speech_types = {
            ObservationType.SPEECH_PRESENT,
            ObservationType.CROSS_MODAL_MATCH,
        }
        return [o for o in (self._observations or []) if o.observation_type in speech_types]

    def get_cross_modal_conflicts(self) -> list[MultimodalObservation]:
        """Retrieve observations where cross-modal divergence or conflict was identified."""
        self._ensure_loaded()
        return [
            o
            for o in (self._observations or [])
            if o.observation_type == ObservationType.CROSS_MODAL_CONFLICT
        ]

    def get_ungrounded_observations(self) -> list[MultimodalObservation]:
        """Retrieve observations that lack physical/perceptual grounding."""
        self._ensure_loaded()
        return [o for o in (self._observations or []) if not o.grounded]

    def get_observations_in_time_range(
        self, start_ms: float, end_ms: float
    ) -> list[MultimodalObservation]:
        """Retrieve observations within a relative time slice [start_ms, end_ms]."""
        self._ensure_loaded()
        return [
            o
            for o in (self._observations or [])
            if start_ms <= o.relative_time_ms <= end_ms
        ]

    def get_supporting_evidence(self, observation_id: str) -> list[MultimodalEvidenceRef]:
        """Return explicit evidence references supporting a given observation."""
        self._ensure_loaded()
        for obs in (self._observations or []):
            if obs.observation_id == observation_id:
                return obs.evidence_refs
        return []

    def get_active_window_at(self, relative_time_ms: float) -> Optional[dict[str, Any]]:
        """Identify which application and window was active at a given timestamp."""
        self._ensure_loaded()
        for win in (self._windows or []):
            if win.start_time_ms <= relative_time_ms <= win.end_time_ms:
                return {
                    "application": win.active_application,
                    "window_title": win.active_window_title,
                    "window_id": win.window_id,
                }
        return None
