"""Deterministic multimodal grounding engine associating events, vision, and speech."""

import math
from typing import Any, Optional

from teach_a_skill.multimodal.context import MultimodalContext
from teach_a_skill.multimodal.models import (
    ModalityType,
    MultimodalEvidenceRef,
    MultimodalObservation,
    ObservationType,
)
from teach_a_skill.perception.models import BoundingBox, TextRegion, UIElement
from teach_a_skill.representation.models import CanonicalEvent, CanonicalEventType


class MultimodalGroundingEngine:
    """Computes deterministic spatial and temporal associations across modalities."""

    def __init__(
        self,
        pointer_proximity_threshold_px: float = 60.0,
        temporal_speech_proximity_ms: float = 3000.0,
    ) -> None:
        self.pointer_proximity_threshold_px = pointer_proximity_threshold_px
        self.temporal_speech_proximity_ms = temporal_speech_proximity_ms

    def ground_context(self, context: MultimodalContext) -> list[MultimodalObservation]:
        """Produce factual grounded observations for a single temporal multimodal context."""
        observations: list[MultimodalObservation] = []
        session_id = context.window.session_id
        w_ms = context.window.start_time_ms
        w_ts_ns = context.window.start_timestamp_ns

        # 1. Window & Application state observation
        if context.window.active_application or context.window.active_window_title:
            app = context.window.active_application or "Unknown"
            title = context.window.active_window_title or "Untitled"
            desc = f"Application '{app}' was active with window title '{title}'."

            evidence: list[MultimodalEvidenceRef] = []
            if context.events:
                first_ev = context.events[0]
                ev_id = getattr(first_ev, "event_id", getattr(first_ev, "canonical_event_id", "cevt_0"))
                ts_ns = getattr(first_ev, "relative_time_ns", getattr(first_ev, "timestamp_ns", int(first_ev.relative_time_ms * 1_000_000)))
                evidence.append(
                    MultimodalEvidenceRef(
                        evidence_type="canonical_event",
                        evidence_id=ev_id,
                        modality=ModalityType.WINDOW_CONTEXT.value,
                        timestamp_ns=ts_ns,
                        relative_time_ms=first_ev.relative_time_ms,
                        details={"app_name": app, "title": title},
                    )
                )

            observations.append(
                MultimodalObservation(
                    observation_id=f"obs_app_{context.window.window_id}",
                    session_id=session_id,
                    observation_type=ObservationType.APPLICATION_STATE,
                    description=desc,
                    timestamp_ns=w_ts_ns,
                    relative_time_ms=w_ms,
                    evidence_refs=evidence,
                    supporting_modalities=[ModalityType.WINDOW_CONTEXT.value],
                    confidence=1.0,
                    provider="deterministic",
                    model_id="deterministic_grounding",
                    model_version="1.0.0",
                    fingerprint=f"app_{app}_{title}",
                    grounded=True,
                )
            )

        # 2. Pointer interaction & UI Element / OCR proximity
        if context.pointer_position:
            px, py = context.pointer_position
            nearest_elem: Optional[UIElement] = None
            min_elem_dist = float("inf")
            inside_elem: Optional[UIElement] = None

            for el in context.ui_elements:
                b = el.bbox
                if b.contains(px, py):
                    inside_elem = el
                    break

                # Distance to center
                cx = b.x + (b.width / 2.0)
                cy = b.y + (b.height / 2.0)
                dist = math.hypot(px - cx, py - cy)
                if dist < min_elem_dist:
                    min_elem_dist = dist
                    nearest_elem = el

            target_el = inside_elem or (
                nearest_elem if min_elem_dist <= self.pointer_proximity_threshold_px else None
            )

            # Nearest OCR text
            nearest_tr: Optional[TextRegion] = None
            inside_tr: Optional[TextRegion] = None
            min_tr_dist = float("inf")

            for tr in context.text_regions:
                b = tr.bbox
                if b.contains(px, py):
                    inside_tr = tr
                    break
                cx = b.x + (b.width / 2.0)
                cy = b.y + (b.height / 2.0)
                dist = math.hypot(px - cx, py - cy)
                if dist < min_tr_dist:
                    min_tr_dist = dist
                    nearest_tr = tr

            target_tr = inside_tr or (
                nearest_tr if min_tr_dist <= self.pointer_proximity_threshold_px else None
            )

            if target_el or target_tr:
                target_desc_parts = []
                evidence_refs: list[MultimodalEvidenceRef] = []
                supporting_mods = [ModalityType.POINTER.value]

                # Pointer evidence from trigger event
                def matches_trigger(e: Any) -> bool:
                    eid = getattr(e, "event_id", getattr(e, "canonical_event_id", ""))
                    return eid == context.window.trigger_event_id

                trigger_ev = next(
                    (e for e in context.events if matches_trigger(e)),
                    context.events[0] if context.events else None,
                )
                if trigger_ev:
                    t_eid = getattr(trigger_ev, "event_id", getattr(trigger_ev, "canonical_event_id", "cevt_trig"))
                    t_ts_ns = getattr(trigger_ev, "relative_time_ns", getattr(trigger_ev, "timestamp_ns", int(trigger_ev.relative_time_ms * 1_000_000)))
                    t_type_val = getattr(trigger_ev, "canonical_event_type", getattr(trigger_ev, "event_type", ""))
                    evidence_refs.append(
                        MultimodalEvidenceRef(
                            evidence_type="canonical_event",
                            evidence_id=t_eid,
                            modality=ModalityType.POINTER.value,
                            timestamp_ns=t_ts_ns,
                            relative_time_ms=trigger_ev.relative_time_ms,
                            details={"x": px, "y": py, "event_type": str(t_type_val)},
                        )
                    )

                if target_el:
                    target_desc_parts.append(
                        f"UI element '{target_el.element_type.value}' ({target_el.element_id})"
                    )
                    supporting_mods.append(ModalityType.UI_ELEMENT.value)
                    evidence_refs.append(
                        MultimodalEvidenceRef(
                            evidence_type="ui_element",
                            evidence_id=target_el.element_id,
                            modality=ModalityType.UI_ELEMENT.value,
                            timestamp_ns=w_ts_ns,
                            relative_time_ms=w_ms,
                            bounding_box=target_el.bbox,
                            details={"element_type": str(target_el.element_type)},
                        )
                    )

                if target_tr:
                    target_desc_parts.append(f"visible text '{target_tr.text}'")
                    supporting_mods.append(ModalityType.OCR_TEXT.value)
                    evidence_refs.append(
                        MultimodalEvidenceRef(
                            evidence_type="ocr_region",
                            evidence_id=target_tr.region_id,
                            modality=ModalityType.OCR_TEXT.value,
                            timestamp_ns=w_ts_ns,
                            relative_time_ms=w_ms,
                            bounding_box=target_tr.bbox,
                            details={"text": target_tr.text, "confidence": target_tr.confidence},
                        )
                    )

                obs_desc = f"Pointer at ({px:.1f}, {py:.1f}) was co-located with {' and '.join(target_desc_parts)}."
                t_str = str(getattr(trigger_ev, "canonical_event_type", getattr(trigger_ev, "event_type", "")))
                is_click = any(k in t_str for k in ("CLICK", "DOWN")) if trigger_ev else False
                obs_type = (
                    ObservationType.POINTER_CLICK_TARGET
                    if is_click
                    else ObservationType.POINTER_PROXIMITY
                )

                observations.append(
                    MultimodalObservation(
                        observation_id=f"obs_ptr_{context.window.window_id}",
                        session_id=session_id,
                        observation_type=obs_type,
                        description=obs_desc,
                        timestamp_ns=w_ts_ns,
                        relative_time_ms=w_ms,
                        evidence_refs=evidence_refs,
                        supporting_modalities=supporting_mods,
                        confidence=0.95 if (inside_elem or inside_tr) else 0.80,
                        provider="deterministic",
                        model_id="deterministic_grounding",
                        model_version="1.0.0",
                        fingerprint=f"ptr_{px}_{py}_{target_el.element_id if target_el else 'none'}",
                        grounded=True,
                    )
                )

        # 3. Speech & Spoken Words Grounding
        for seg in context.transcripts:
            seg_start_ns = getattr(seg, "start_monotonic_ns", getattr(seg, "start_timestamp_ns", 0))
            seg_end_ns = getattr(seg, "end_monotonic_ns", getattr(seg, "end_timestamp_ns", seg_start_ns))
            seg_conf = getattr(seg, "confidence", 0.85) or 0.85

            evidence_refs = [
                MultimodalEvidenceRef(
                    evidence_type="transcript_segment",
                    evidence_id=seg.segment_id,
                    modality=ModalityType.SPEECH_TRANSCRIPT.value,
                    timestamp_ns=seg_start_ns,
                    relative_time_ms=seg_start_ns / 1_000_000.0,
                    details={"text": seg.text, "confidence": seg_conf},
                )
            ]
            supporting_mods = [ModalityType.SPEECH_TRANSCRIPT.value]

            # Cross-modal lexical match: check if spoken words match any visible OCR text
            spoken_words = {w.lower().strip(".,!?:;\"'") for w in seg.text.split() if len(w) > 3}
            matching_texts = []
            for tr in context.text_regions:
                tr_words = {w.lower().strip(".,!?:;\"'") for w in tr.text.split() if len(w) > 3}
                shared = spoken_words.intersection(tr_words)
                if shared:
                    matching_texts.append((tr, shared))
                    evidence_refs.append(
                        MultimodalEvidenceRef(
                            evidence_type="ocr_region",
                            evidence_id=tr.region_id,
                            modality=ModalityType.OCR_TEXT.value,
                            timestamp_ns=w_ts_ns,
                            relative_time_ms=w_ms,
                            bounding_box=tr.bbox,
                            details={"matched_words": list(shared)},
                        )
                    )
                    supporting_mods.append(ModalityType.OCR_TEXT.value)

            if matching_texts:
                shared_summary = ", ".join(f"'{tr.text}' (words: {list(sw)})" for tr, sw in matching_texts[:3])
                desc = f"Spoken phrase '{seg.text}' shared vocabulary with visible text: {shared_summary}."
                obs_type = ObservationType.CROSS_MODAL_MATCH
                conf = 0.90
            else:
                desc = f"Speech uttered during window: '{seg.text}'."
                obs_type = ObservationType.SPEECH_PRESENT
                conf = seg_conf

            observations.append(
                MultimodalObservation(
                    observation_id=f"obs_spk_{seg.segment_id}_{context.window.window_id}",
                    session_id=session_id,
                    observation_type=obs_type,
                    description=desc,
                    timestamp_ns=seg_start_ns,
                    relative_time_ms=round(seg_start_ns / 1_000_000.0, 2),
                    duration_ms=round((seg_end_ns - seg_start_ns) / 1_000_000.0, 2),
                    evidence_refs=evidence_refs,
                    supporting_modalities=list(set(supporting_mods)),
                    confidence=conf,
                    provider="deterministic",
                    model_id="deterministic_grounding",
                    model_version="1.0.0",
                    fingerprint=f"speech_{seg.segment_id}",
                    grounded=True,
                )
            )

        # 4. Typed Annotations Grounding
        for ann in context.annotations:
            ann_ts_ns = getattr(ann, "start_monotonic_ns", getattr(ann, "created_monotonic_ns", getattr(ann, "timestamp_ns", 0)))
            ann_cat = str(getattr(ann, "type", getattr(ann, "category", "instruction")))
            evidence_refs = [
                MultimodalEvidenceRef(
                    evidence_type="annotation",
                    evidence_id=ann.annotation_id,
                    modality=ModalityType.TYPED_ANNOTATION.value,
                    timestamp_ns=ann_ts_ns,
                    relative_time_ms=ann_ts_ns / 1_000_000.0,
                    details={"text": ann.text, "category": ann_cat},
                )
            ]
            observations.append(
                MultimodalObservation(
                    observation_id=f"obs_ann_{ann.annotation_id}_{context.window.window_id}",
                    session_id=session_id,
                    observation_type=ObservationType.ANNOTATION_PRESENT,
                    description=f"Typed teaching instruction was attached: '{ann.text}'.",
                    timestamp_ns=ann_ts_ns,
                    relative_time_ms=round(ann_ts_ns / 1_000_000.0, 2),
                    evidence_refs=evidence_refs,
                    supporting_modalities=[ModalityType.TYPED_ANNOTATION.value],
                    confidence=1.0,
                    provider="deterministic",
                    model_id="deterministic_grounding",
                    model_version="1.0.0",
                    fingerprint=f"ann_{ann.annotation_id}",
                    grounded=True,
                )
            )

        return observations
