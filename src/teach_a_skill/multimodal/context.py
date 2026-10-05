"""Context assembly engine creating bounded temporal multimodal windows."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from teach_a_skill.core.logging import get_logger
from teach_a_skill.multimodal.models import TemporalWindow
from teach_a_skill.perception.models import TextRegion, UIElement
from teach_a_skill.perception.storage import PerceptionStorage
from teach_a_skill.representation.models import CanonicalEvent, CanonicalEventType
from teach_a_skill.representation.storage import RepresentationStorage
from teach_a_skill.storage.manager import StorageManager
from teach_a_skill.teaching.annotations.model import TeachingAnnotation
from teach_a_skill.teaching.transcript.segment import TranscriptSegment

logger = get_logger("teach_a_skill.multimodal.context")


@dataclass
class MultimodalContext:
    """Rich in-memory context bundle for a single temporal window."""

    window: TemporalWindow
    events: list[CanonicalEvent] = field(default_factory=list)
    ui_elements: list[UIElement] = field(default_factory=list)
    text_regions: list[TextRegion] = field(default_factory=list)
    transcripts: list[TranscriptSegment] = field(default_factory=list)
    annotations: list[TeachingAnnotation] = field(default_factory=list)
    primary_frame_id: Optional[str] = None
    primary_frame_path: Optional[Path] = None
    pointer_position: Optional[tuple[float, float]] = None


class MultimodalContextBuilder:
    """Assembles temporal slices across canonical events, perception, and speech."""

    def __init__(
        self,
        storage_manager: StorageManager,
        window_duration_ms: float = 2000.0,
        pre_event_window_ms: float = 500.0,
        max_context_elements: int = 50,
    ) -> None:
        self.storage_manager = storage_manager
        self.window_duration_ms = window_duration_ms
        self.pre_event_window_ms = pre_event_window_ms
        self.max_context_elements = max_context_elements

    def build_contexts_for_session(
        self,
        session_id: str,
        max_windows: Optional[int] = None,
    ) -> list[MultimodalContext]:
        """Construct bounded multimodal contexts across an entire session."""
        rep_storage = RepresentationStorage(self.storage_manager, session_id)
        if rep_storage.exists():
            all_events = list(rep_storage.stream_canonical_events())
        else:
            all_events = []

        if not all_events:
            logger.debug(f"No canonical events found for session '{session_id}'")
            return []

        # Perception query engine if perception partition exists
        perception_engine = None
        perc_storage = PerceptionStorage(self.storage_manager, session_id)
        if perc_storage.exists():
            try:
                from teach_a_skill.perception.query import PerceptionQueryEngine

                perception_engine = PerceptionQueryEngine(self.storage_manager, session_id)
            except Exception as e:
                logger.debug(f"Could not load perception query engine: {e}")

        # 2. Fetch teaching layer evidence if available
        teaching_dir = self.storage_manager.get_path("recordings", session_id) / "teaching"
        transcripts: list[TranscriptSegment] = []
        annotations: list[TeachingAnnotation] = []

        if teaching_dir.exists():
            try:
                from teach_a_skill.teaching.storage import TeachingStorage

                t_storage = TeachingStorage(self.storage_manager, session_id)
                transcripts = t_storage.read_transcript_segments()
                annotations = t_storage.read_annotations()
            except Exception as e:
                logger.debug(f"Teaching evidence unreadable or empty: {e}")

        # 3. Identify trigger events that define anchor interaction windows
        trigger_types = {
            "CLICK",
            "POINTER_DOWN",
            "KEY_DOWN",
            "WINDOW_FOCUS",
            "WINDOW_MOVED",
            "WINDOW_RESIZED",
            "MOUSE_CLICK",
            "MOUSE_DOWN",
            "WINDOW_FOCUS_CHANGED",
        }

        def get_etype_str(ev: Any) -> str:
            val = getattr(ev, "canonical_event_type", getattr(ev, "event_type", ""))
            return str(val.value if hasattr(val, "value") else val)

        anchor_events = [e for e in all_events if get_etype_str(e) in trigger_types]
        if not anchor_events:
            # Fall back to first, middle, last events if no explicit interaction triggers
            step = max(1, len(all_events) // 5)
            anchor_events = all_events[::step]

        if max_windows is not None and max_windows > 0:
            anchor_events = anchor_events[:max_windows]

        contexts: list[MultimodalContext] = []
        rec_dir = self.storage_manager.get_path("recordings", session_id)

        for w_idx, anchor in enumerate(anchor_events):
            anchor_ms = anchor.relative_time_ms
            w_start_ms = max(0.0, anchor_ms - self.pre_event_window_ms)
            w_end_ms = w_start_ms + self.window_duration_ms

            # Temporal events within window
            window_events = [
                e for e in all_events if w_start_ms <= e.relative_time_ms <= w_end_ms
            ]

            # Pointer position from anchor if pointer event
            pointer_pos = None
            ax = getattr(anchor, "raw_x", getattr(anchor, "normalized_x", getattr(anchor, "x", None)))
            ay = getattr(anchor, "raw_y", getattr(anchor, "normalized_y", getattr(anchor, "y", None)))
            if ax is not None and ay is not None:
                pointer_pos = (float(ax), float(ay))

            # Application & window context
            active_app = getattr(anchor, "application", getattr(anchor, "app_name", None))
            if not active_app and window_events:
                active_app = getattr(window_events[0], "application", getattr(window_events[0], "app_name", None))

            active_title = getattr(anchor, "window_title", None)
            if not active_title and window_events:
                active_title = getattr(window_events[0], "window_title", None)

            # Nearest primary perception frame
            primary_frame_id = getattr(anchor, "frame_reference", getattr(anchor, "associated_frame_id", None))
            if not primary_frame_id and perception_engine:
                # Query nearest frame temporally
                ts_ns = getattr(anchor, "relative_time_ns", getattr(anchor, "timestamp_ns", int(anchor_ms * 1_000_000)))
                p_ctx = perception_engine.get_perception_context(ts_ns)
                if p_ctx:
                    primary_frame_id = p_ctx.frame_id

            ui_elements: list[UIElement] = []
            text_regions: list[TextRegion] = []
            frame_path = None

            if primary_frame_id and perception_engine:
                p_frame = perception_engine.get_perception_frame(primary_frame_id)
                if p_frame:
                    frame_path = rec_dir / p_frame.frame_path
                ui_elements = perception_engine.get_ui_elements(primary_frame_id)
                text_regions = perception_engine.get_text_regions(primary_frame_id)

            # Limit UI elements to bounded count
            if len(ui_elements) > self.max_context_elements:
                ui_elements = ui_elements[: self.max_context_elements]

            # Spoken transcripts overlapping this window (converting ns to ms)
            def get_t_start(t: Any) -> float:
                return float(getattr(t, "start_monotonic_ns", getattr(t, "start_timestamp_ns", 0))) / 1_000_000.0

            def get_t_end(t: Any) -> float:
                return float(getattr(t, "end_monotonic_ns", getattr(t, "end_timestamp_ns", 0))) / 1_000_000.0

            w_transcripts = [
                t for t in transcripts
                if get_t_start(t) <= w_end_ms and get_t_end(t) >= w_start_ms
            ]

            # Annotations overlapping this window
            def get_a_time(a: Any) -> float:
                return float(getattr(a, "start_monotonic_ns", getattr(a, "created_monotonic_ns", getattr(a, "timestamp_ns", 0)))) / 1_000_000.0

            w_annotations = [
                a for a in annotations
                if w_start_ms <= get_a_time(a) <= w_end_ms
            ]

            anchor_id = getattr(anchor, "event_id", getattr(anchor, "canonical_event_id", f"cevt_{w_idx}"))
            w_id = f"win_{w_idx + 1:04d}_{session_id}"
            temp_window = TemporalWindow(
                window_id=w_id,
                session_id=session_id,
                start_time_ms=round(w_start_ms, 2),
                end_time_ms=round(w_end_ms, 2),
                start_timestamp_ns=int(w_start_ms * 1_000_000),
                end_timestamp_ns=int(w_end_ms * 1_000_000),
                trigger_event_id=anchor_id,
                canonical_event_ids=[
                    getattr(e, "event_id", getattr(e, "canonical_event_id", f"cevt_{i}"))
                    for i, e in enumerate(window_events)
                ],
                frame_ids=[primary_frame_id] if primary_frame_id else [],
                ocr_region_ids=[t.region_id for t in text_regions],
                ui_element_ids=[e.element_id for e in ui_elements],
                transcript_segment_ids=[t.segment_id for t in w_transcripts],
                annotation_ids=[a.annotation_id for a in w_annotations],
                active_application=active_app,
                active_window_title=active_title,
                pointer_coordinates=pointer_pos,
            )

            contexts.append(
                MultimodalContext(
                    window=temp_window,
                    events=window_events,
                    ui_elements=ui_elements,
                    text_regions=text_regions,
                    transcripts=w_transcripts,
                    annotations=w_annotations,
                    primary_frame_id=primary_frame_id,
                    primary_frame_path=frame_path,
                    pointer_position=pointer_pos,
                )
            )

        return contexts
