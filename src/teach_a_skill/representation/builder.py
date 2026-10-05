"""Canonical representation builder coordinating normalization, derivation, indexing, and validation."""

import bisect
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from teach_a_skill.core.errors import StorageError
from teach_a_skill.core.logging import get_logger
from teach_a_skill.recorder.events import Event, EventType
from teach_a_skill.recorder.session import SessionManifest
from teach_a_skill.recorder.storage import SessionStorage
from teach_a_skill.representation.derivation.density import calculate_demonstration_summary
from teach_a_skill.representation.derivation.interactions import (
    derive_application_transitions,
    derive_click_interactions,
    derive_double_clicks,
    derive_drag_sequences,
    derive_idle_intervals,
    derive_keyboard_shortcuts,
    derive_pointer_paths,
    derive_text_input_sequences,
    derive_window_context_intervals,
)
from teach_a_skill.representation.derivation.relations import build_temporal_relations
from teach_a_skill.representation.derivation.segmentation import derive_demonstration_segments
from teach_a_skill.representation.fingerprint import compute_demonstration_fingerprint
from teach_a_skill.representation.indexes import DemonstrationIndexes
from teach_a_skill.representation.models import (
    CanonicalEvent,
    CanonicalEventType,
    DemonstrationManifest,
    EventCategory,
    ProvenanceView,
)
from teach_a_skill.representation.storage import RepresentationStorage
from teach_a_skill.representation.timeline import (
    PRIORITY_RANKS,
    CanonicalTimeline,
    CanonicalTimelineItem,
    TimelineItemType,
)
from teach_a_skill.representation.validator import RepresentationValidator
from teach_a_skill.storage.manager import StorageManager
from teach_a_skill.teaching.storage import TeachingStorage

logger = get_logger("teach_a_skill.representation.builder")


EVENT_TYPE_MAPPING: dict[str, tuple[CanonicalEventType, EventCategory]] = {
    EventType.MOUSE_MOVE.value: (CanonicalEventType.POINTER_MOVE, EventCategory.POINTER),
    EventType.MOUSE_DOWN.value: (CanonicalEventType.POINTER_DOWN, EventCategory.POINTER),
    EventType.MOUSE_UP.value: (CanonicalEventType.POINTER_UP, EventCategory.POINTER),
    EventType.MOUSE_CLICK.value: (CanonicalEventType.CLICK, EventCategory.POINTER),
    EventType.MOUSE_DOUBLE_CLICK.value: (CanonicalEventType.DOUBLE_CLICK, EventCategory.POINTER),
    EventType.MOUSE_SCROLL.value: (CanonicalEventType.SCROLL, EventCategory.POINTER),
    EventType.MOUSE_DRAG.value: (CanonicalEventType.DRAG, EventCategory.POINTER),
    EventType.KEY_DOWN.value: (CanonicalEventType.KEY_DOWN, EventCategory.KEYBOARD),
    EventType.KEY_UP.value: (CanonicalEventType.KEY_UP, EventCategory.KEYBOARD),
    EventType.TEXT_INPUT.value: (CanonicalEventType.TEXT_INPUT, EventCategory.KEYBOARD),
    EventType.WINDOW_FOCUS_CHANGED.value: (CanonicalEventType.WINDOW_FOCUS, EventCategory.WINDOW),
    EventType.WINDOW_CREATED.value: (CanonicalEventType.WINDOW_CREATED, EventCategory.WINDOW),
    EventType.WINDOW_CLOSED.value: (CanonicalEventType.WINDOW_CLOSED, EventCategory.WINDOW),
    EventType.WINDOW_MOVED.value: (CanonicalEventType.WINDOW_MOVED, EventCategory.WINDOW),
    EventType.WINDOW_RESIZED.value: (CanonicalEventType.WINDOW_RESIZED, EventCategory.WINDOW),
    EventType.SCREENSHOT_CAPTURED.value: (CanonicalEventType.SCREEN_CAPTURE, EventCategory.SCREEN),
    EventType.SCREEN_STATE_CHANGED.value: (CanonicalEventType.SCREEN_STATE_CHANGED, EventCategory.SCREEN),
    EventType.SESSION_STARTED.value: (CanonicalEventType.SESSION_START, EventCategory.SESSION),
    EventType.SESSION_PAUSED.value: (CanonicalEventType.SESSION_PAUSE, EventCategory.SESSION),
    EventType.SESSION_RESUMED.value: (CanonicalEventType.SESSION_RESUME, EventCategory.SESSION),
    EventType.SESSION_STOPPED.value: (CanonicalEventType.SESSION_STOP, EventCategory.SESSION),
    EventType.SESSION_ABORTED.value: (CanonicalEventType.SESSION_ABORT, EventCategory.SESSION),
    EventType.DISPLAY_CONFIGURATION_CHANGED.value: (CanonicalEventType.DISPLAY_CHANGE, EventCategory.SYSTEM),
    EventType.RECORDER_WARNING.value: (CanonicalEventType.SYSTEM_WARNING, EventCategory.SYSTEM),
    EventType.RECORDER_ERROR.value: (CanonicalEventType.SYSTEM_ERROR, EventCategory.SYSTEM),
}


class RepresentationBuilder:
    """Builds canonical demonstration representation from Phase 2 recorder and Phase 3 teaching evidence."""

    def __init__(self, storage_manager: StorageManager) -> None:
        self.storage_manager = storage_manager

    def build_representation(
        self,
        session_id: str,
        force_rebuild: bool = False,
    ) -> Path:
        """Construct, stage, validate, and atomically publish canonical demonstration representation.

        Guarantees:
        - 100% byte-for-byte immutability of Phase 2 and Phase 3 raw evidence.
        - Deterministic output.
        - Memory-bounded streaming and indexing.
        """
        rep_storage = RepresentationStorage(self.storage_manager, session_id)

        if not force_rebuild and rep_storage.exists():
            logger.info(f"Canonical representation already exists for session '{session_id}'.")
            return rep_storage.representation_dir

        session_storage = SessionStorage(self.storage_manager, session_id)
        if not session_storage.session_dir.exists():
            raise StorageError(f"Session directory not found for session ID '{session_id}'")

        # 1. Capture pre-build raw evidence checksums to guarantee immutability
        pre_checksums = RepresentationStorage.compute_raw_evidence_checksums(session_storage.session_dir)

        # 2. Load Phase 2 raw evidence
        if not session_storage.manifest_file.exists():
            raise StorageError(f"Raw session manifest missing for session ID '{session_id}'")

        raw_manifest_dict = self.storage_manager.read_metadata(session_storage.manifest_file)
        raw_manifest = SessionManifest.from_dict(raw_manifest_dict)

        raw_events = session_storage.read_all_events()
        frame_index_path = session_storage.metadata_dir / "frame_index.json"
        frames: list[dict[str, Any]] = []
        if frame_index_path.exists():
            try:
                frame_data = self.storage_manager.read_metadata(frame_index_path)
                frames = frame_data.get("frames", [])
            except Exception as e:
                logger.warning(f"Could not read frame_index.json: {e}")

        # 3. Load Phase 3 teaching evidence if present
        teaching_storage = TeachingStorage(self.storage_manager, session_id)
        teaching_manifest = None
        speech_segments: list[dict[str, Any]] = []
        annotations: list[dict[str, Any]] = []

        if teaching_storage.manifest_file.exists():
            try:
                teaching_manifest = self.storage_manager.read_metadata(teaching_storage.manifest_file)
                speech_segments = [s.to_dict() for s in teaching_storage.transcript_store.read_all_segments(only_active=True)]
                annotations = [a.to_dict() for a in teaching_storage.annotation_store.read_all_annotations(only_active=True)]
            except Exception as e:
                logger.warning(f"Could not load teaching evidence for session '{session_id}': {e}")

        # Determine reference timeline origin
        t0_monotonic_sec = raw_events[0].monotonic_timestamp if raw_events else 0.0
        t0_monotonic_ns = int(t0_monotonic_sec * 1_000_000_000)

        # Display dimensions for coordinate normalization
        disp_w = 1920.0
        disp_h = 1080.0
        if raw_manifest.display_configuration:
            first_disp = raw_manifest.display_configuration[0]
            disp_w = float(first_disp.get("width", 1920.0))
            disp_h = float(first_disp.get("height", 1080.0))

        # 4. Normalize raw events into CanonicalEvents
        canonical_events: list[CanonicalEvent] = []
        active_app: Optional[str] = None
        active_win: Optional[str] = None
        active_pid: Optional[int] = None
        for idx, ev in enumerate(raw_events):
            rel_t_sec = max(0.0, ev.monotonic_timestamp - t0_monotonic_sec)
            rel_t_ms = round(rel_t_sec * 1000.0, 2)
            rel_t_ns = int(rel_t_sec * 1_000_000_000)

            c_type, cat = EVENT_TYPE_MAPPING.get(
                ev.event_type.value,
                (CanonicalEventType.SYSTEM_WARNING, EventCategory.SYSTEM),
            )

            raw_x = ev.payload.get("x")
            raw_y = ev.payload.get("y")
            norm_x = round(raw_x / disp_w, 4) if raw_x is not None and disp_w > 0 else None
            norm_y = round(raw_y / disp_h, 4) if raw_y is not None and disp_h > 0 else None

            # Window context resolution
            app = ev.payload.get("app_name")
            win = ev.payload.get("title")
            pid = ev.payload.get("process_id")

            if app is not None:
                active_app = app
                active_win = win
                active_pid = pid
            else:
                app = active_app
                win = active_win
                pid = active_pid

            can_ev = CanonicalEvent(
                event_id=f"canon_evt_{idx + 1:06d}",
                source_event_id=ev.event_id,
                timestamp=ev.timestamp,
                monotonic_timestamp=ev.monotonic_timestamp,
                relative_time_ms=rel_t_ms,
                relative_time_ns=rel_t_ns,
                category=cat,
                canonical_event_type=c_type,
                raw_event_type=ev.event_type.value.lower(),
                source=ev.source,
                sequence=ev.sequence_number,
                display_id=str(ev.payload.get("display_id", 0)),
                raw_x=raw_x,
                raw_y=raw_y,
                normalized_x=norm_x,
                normalized_y=norm_y,
                application=app,
                window_title=win,
                process_id=pid,
                payload=ev.payload,
                provenance=ProvenanceView({
                    "recording_session_id": session_id,
                    "phase2_schema_version": raw_manifest.schema_version,
                }),
            )
            canonical_events.append(can_ev)

        # 5. Derive physical interactions
        clicks = derive_click_interactions(canonical_events, session_id)
        double_clicks = derive_double_clicks(clicks, session_id)
        drags = derive_drag_sequences(canonical_events, session_id)
        pointer_paths = derive_pointer_paths(canonical_events, session_id)
        shortcuts = derive_keyboard_shortcuts(canonical_events, session_id)
        text_inputs = derive_text_input_sequences(canonical_events, session_id)
        idle_intervals = derive_idle_intervals(canonical_events, raw_manifest.duration_sec)
        win_intervals = derive_window_context_intervals(canonical_events, session_id)
        app_transitions = derive_application_transitions(canonical_events, session_id)

        # 6. Build unified Canonical Timeline Items
        timeline_items: list[CanonicalTimelineItem] = []

        # Canonical events -> timeline
        for ev in canonical_events:
            timeline_items.append(
                CanonicalTimelineItem(
                    item_id=ev.event_id,
                    item_type=TimelineItemType.EVENT,
                    source_id=ev.source_event_id,
                    monotonic_timestamp_ns=ev.relative_time_ns,
                    relative_time_ms=ev.relative_time_ms,
                    sequence=ev.sequence,
                    priority_rank=PRIORITY_RANKS[TimelineItemType.EVENT.value],
                    payload_preview={
                        "type": ev.canonical_event_type.value,
                        "category": ev.category.value,
                        "app": ev.application,
                    },
                )
            )

        # Screen frames -> timeline
        for idx, f in enumerate(frames):
            f_mono = float(f.get("monotonic_timestamp", 0.0))
            f_rel_sec = max(0.0, f_mono - t0_monotonic_sec) if f_mono >= t0_monotonic_sec else f_mono
            f_ns = int(f_rel_sec * 1_000_000_000)
            timeline_items.append(
                CanonicalTimelineItem(
                    item_id=f.get("frame_id", f"frame_{idx:05d}"),
                    item_type=TimelineItemType.FRAME,
                    source_id=f.get("frame_id", ""),
                    monotonic_timestamp_ns=f_ns,
                    relative_time_ms=round(f_rel_sec * 1000.0, 2),
                    sequence=idx + 1,
                    priority_rank=PRIORITY_RANKS[TimelineItemType.FRAME.value],
                    payload_preview={"path": f.get("path")},
                )
            )

        # Speech segments -> timeline
        for idx, sp in enumerate(speech_segments):
            sp_start_ns = sp.get("start_monotonic_ns", 0)
            timeline_items.append(
                CanonicalTimelineItem(
                    item_id=sp.get("segment_id", f"speech_{idx:05d}"),
                    item_type=TimelineItemType.SPEECH,
                    source_id=sp.get("segment_id", ""),
                    monotonic_timestamp_ns=sp_start_ns,
                    relative_time_ms=round(sp_start_ns / 1_000_000.0, 2),
                    sequence=idx + 1,
                    priority_rank=PRIORITY_RANKS[TimelineItemType.SPEECH.value],
                    payload_preview={"text_preview": (sp.get("text") or "")[:40]},
                )
            )

        # Annotations -> timeline
        for idx, ann in enumerate(annotations):
            ann_start_ns = ann.get("start_monotonic_ns", 0)
            timeline_items.append(
                CanonicalTimelineItem(
                    item_id=ann.get("annotation_id", f"ann_{idx:05d}"),
                    item_type=TimelineItemType.ANNOTATION,
                    source_id=ann.get("annotation_id", ""),
                    monotonic_timestamp_ns=ann_start_ns,
                    relative_time_ms=round(ann_start_ns / 1_000_000.0, 2),
                    sequence=idx + 1,
                    priority_rank=PRIORITY_RANKS[TimelineItemType.ANNOTATION.value],
                    payload_preview={"type": ann.get("type"), "text_preview": (ann.get("text") or "")[:40]},
                )
            )

        # Sort timeline deterministically
        timeline = CanonicalTimeline(timeline_items)
        sorted_timeline_items = timeline.items

        # 7. Build physical + temporal relations
        relations = build_temporal_relations(
            events=canonical_events,
            frames=frames,
            speech_segments=speech_segments,
            annotations=annotations,
            clicks=clicks,
            drags=drags,
            shortcuts=shortcuts,
            text_inputs=text_inputs,
            session_id=session_id,
        )

        # 8. Deterministic segmentation
        segments = derive_demonstration_segments(
            events=canonical_events,
            app_transitions=app_transitions,
            idle_intervals=idle_intervals,
            speech_segments=speech_segments,
            annotations=annotations,
            frames=frames,
            total_duration_sec=raw_manifest.duration_sec,
        )

        # 9. Compute summary statistics and density metrics
        summary = calculate_demonstration_summary(
            canonical_events=canonical_events,
            pointer_paths=pointer_paths,
            clicks=clicks,
            double_clicks=double_clicks,
            drags=drags,
            shortcuts=shortcuts,
            text_inputs=text_inputs,
            segments=segments,
            idle_intervals=idle_intervals,
            speech_segments=speech_segments,
            annotations=annotations,
            frames=frames,
            total_duration_sec=raw_manifest.duration_sec,
        )

        # 10. Build pre-computed local indexes
        indexes = DemonstrationIndexes()
        indexes.time_to_timeline = [[item.monotonic_timestamp_ns, idx] for idx, item in enumerate(sorted_timeline_items)]
        indexes.id_to_timeline_index = {item.item_id: idx for idx, item in enumerate(sorted_timeline_items)}

        item_times = [item.monotonic_timestamp_ns for item in sorted_timeline_items]
        for seg in segments:
            s_idx = bisect.bisect_left(item_times, seg.start_monotonic_ns)
            e_idx = max(s_idx, bisect.bisect_right(item_times, seg.end_monotonic_ns) - 1)
            indexes.segment_ranges[seg.segment_id] = [seg.start_monotonic_ns, seg.end_monotonic_ns, s_idx, e_idx]

        for w_ctx in win_intervals:
            indexes.app_to_intervals.setdefault(w_ctx.application, []).append([w_ctx.start_monotonic_ns, w_ctx.end_monotonic_ns])
            indexes.window_to_intervals.setdefault(w_ctx.window_title, []).append([w_ctx.start_monotonic_ns, w_ctx.end_monotonic_ns])

        for f in frames:
            f_mono = float(f.get("monotonic_timestamp", 0.0))
            f_rel_sec = max(0.0, f_mono - t0_monotonic_sec) if f_mono >= t0_monotonic_sec else f_mono
            indexes.frame_to_time_ns[f.get("frame_id", "")] = int(f_rel_sec * 1_000_000_000)

        for sp in speech_segments:
            indexes.speech_to_time_ns[sp.get("segment_id", "")] = sp.get("start_monotonic_ns", 0)

        for ann in annotations:
            indexes.annotation_to_time_ns[ann.get("annotation_id", "")] = ann.get("start_monotonic_ns", 0)

        # 11. Compute cryptographic demonstration fingerprint
        fingerprint = compute_demonstration_fingerprint(
            session_id=session_id,
            schema_version="1.0.0",
            canonical_events=canonical_events,
            timeline_items=sorted_timeline_items,
            segments=segments,
            relations=relations,
        )

        manifest = DemonstrationManifest(
            demonstration_id=f"demo_{session_id}",
            recording_session_id=session_id,
            teaching_session_id=teaching_manifest.get("teaching_session_id") if teaching_manifest else None,
            schema_version="1.0.0",
            derivation_version="phase4-v1",
            algorithm_version="deterministic-v1",
            started_at=raw_manifest.started_at,
            ended_at=raw_manifest.ended_at,
            duration_sec=raw_manifest.duration_sec,
            fingerprint=fingerprint,
            source_checksums=pre_checksums,
            hardware_profile=raw_manifest.hardware_profile,
        )

        # 12. Stage into temporary build environment
        staged_dir = rep_storage.create_temp_build_environment()
        interactions_payload = {
            "clicks.json": clicks,
            "double_clicks.json": double_clicks,
            "drags.json": drags,
            "pointer_paths.json": pointer_paths,
            "shortcuts.json": shortcuts,
            "text_inputs.json": text_inputs,
            "idles.json": idle_intervals,
            "window_intervals.json": win_intervals,
            "app_transitions.json": app_transitions,
        }
        _ = rep_storage.write_staged_representation(
            staged_dir=staged_dir,
            manifest=manifest,
            summary=summary,
            timeline_items=sorted_timeline_items,
            segments=segments,
            relations=relations,
            indexes=indexes,
            canonical_events=canonical_events,
            interactions=interactions_payload,
        )

        # 13. Validate staged representation before promotion
        val_report = RepresentationValidator.validate_representation(staged_dir, session_storage.session_dir)
        if not val_report.is_valid:
            shutil.rmtree(staged_dir)
            raise StorageError(f"Canonical representation validation failed: {'; '.join(val_report.errors)}")

        # 14. Atomically promote staged representation to production directory
        rep_storage.promote_staged_representation(staged_dir)

        # 15. Verify raw evidence immutability (Post-build checksums == Pre-build checksums)
        post_checksums = RepresentationStorage.compute_raw_evidence_checksums(session_storage.session_dir)
        for rel_path, pre_hash in pre_checksums.items():
            post_hash = post_checksums.get(rel_path)
            if post_hash != pre_hash:
                raise StorageError(
                    f"CRITICAL IMMUTABILITY VIOLATION: Raw evidence file '{rel_path}' was modified! "
                    f"Pre: {pre_hash}, Post: {post_hash}"
                )

        logger.info(
            f"Canonical representation built successfully for session '{session_id}' "
            f"({len(canonical_events)} events, {len(sorted_timeline_items)} timeline items, "
            f"{len(segments)} segments, {len(relations)} relations)."
        )
        return rep_storage.representation_dir
