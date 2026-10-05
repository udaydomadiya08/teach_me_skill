"""Cross-modal fusion engine and hallucination control."""

import re
from typing import Any, Optional

from teach_a_skill.core.logging import get_logger
from teach_a_skill.multimodal.context import MultimodalContext
from teach_a_skill.multimodal.grounding import MultimodalGroundingEngine
from teach_a_skill.multimodal.models import (
    ModalityType,
    MultimodalEvidenceRef,
    MultimodalObservation,
    ObservationType,
)

logger = get_logger("teach_a_skill.multimodal.fusion")

# Strict semantic boundary prohibition pattern: Phase 7+ concepts
PROHIBITED_SEMANTIC_PATTERNS = [
    r"\buser(?:\'s)?\s+(?:intent|goal|objective|desire|plan)\b",
    r"\b(?:wants?|trying|attempting)\s+to\b",
    r"\btask\s+(?:goal|decomposition|plan)\b",
    r"\bskill\s+(?:compilation|execution|procedure)\b",
    r"\bnext\s+action\s+should\s+be\b",
    r"\baction\s+plan\b",
    r"\bautomation\s+plan\b",
]
_PROHIBITED_REGEX = re.compile("|".join(PROHIBITED_SEMANTIC_PATTERNS), re.IGNORECASE)


class MultimodalFusionEngine:
    """Combines deterministic physical/perceptual grounding with model observations.
    
    Responsibilities:
    1. Cross-modal corroboration (validating model claims against deterministic ground truth).
    2. Hallucination suppression (marking ungrounded claims with grounded=False).
    3. Conflict detection (generating CROSS_MODAL_CONFLICT when modalities disagree).
    4. Strict semantic boundary enforcement (stripping / rejecting intentional reasoning).
    """

    def __init__(
        self,
        grounding_engine: Optional[MultimodalGroundingEngine] = None,
        min_grounding_confidence: float = 0.50,
    ) -> None:
        self.grounding_engine = grounding_engine or MultimodalGroundingEngine()
        self.min_grounding_confidence = min_grounding_confidence

    def fuse(
        self,
        context: MultimodalContext,
        provider_observations: list[MultimodalObservation],
    ) -> list[MultimodalObservation]:
        """Perform multimodal fusion, evidence validation, and hallucination filtering."""
        # 1. Generate authoritative deterministic observations
        deterministic_obs = self.grounding_engine.ground_context(context)

        # Build index of grounded evidence available in this context
        available_ocr_regions = {tr.region_id: tr for tr in context.text_regions}
        available_ui_elements = {el.element_id: el for el in context.ui_elements}
        available_transcripts = {seg.segment_id: seg for seg in context.transcripts}
        available_events = {
            getattr(ev, "event_id", getattr(ev, "canonical_event_id", f"cevt_{i}")): ev
            for i, ev in enumerate(context.events)
        }

        fused_results: list[MultimodalObservation] = list(deterministic_obs)
        existing_ids = {o.observation_id for o in fused_results}

        # 2. Corroborate and filter provider observations
        for obs in provider_observations:
            if obs.observation_id in existing_ids:
                continue
            sanitized_obs = self._corroborate_and_sanitize(
                obs=obs,
                context=context,
                available_ocr=available_ocr_regions,
                available_ui=available_ui_elements,
                available_transcripts=available_transcripts,
                available_events=available_events,
            )
            if sanitized_obs is not None:
                fused_results.append(sanitized_obs)
                existing_ids.add(sanitized_obs.observation_id)

        # 3. Detect cross-modal divergence / conflict
        conflict_obs = self._detect_cross_modal_conflicts(context, fused_results)
        fused_results.extend(conflict_obs)

        return fused_results

    def _corroborate_and_sanitize(
        self,
        obs: MultimodalObservation,
        context: MultimodalContext,
        available_ocr: dict[str, Any],
        available_ui: dict[str, Any],
        available_transcripts: dict[str, Any],
        available_events: dict[str, Any],
    ) -> Optional[MultimodalObservation]:
        """Check observation against evidence, suppress hallucinations, and enforce boundary."""
        # Check for Phase 7 boundary violation in description
        if _PROHIBITED_REGEX.search(obs.description):
            logger.warning(
                f"Suppressed observation '{obs.observation_id}' due to Phase 7 semantic boundary violation: {obs.description}"
            )
            return None

        # Check evidence grounding
        valid_refs: list[MultimodalEvidenceRef] = []
        for ref in obs.evidence_refs:
            if ref.evidence_type == "ocr_region" and ref.evidence_id in available_ocr:
                valid_refs.append(ref)
            elif ref.evidence_type == "ui_element" and ref.evidence_id in available_ui:
                valid_refs.append(ref)
            elif (
                ref.evidence_type == "transcript_segment"
                and ref.evidence_id in available_transcripts
            ):
                valid_refs.append(ref)
            elif ref.evidence_type == "canonical_event" and ref.evidence_id in available_events:
                valid_refs.append(ref)
            elif ref.evidence_type == "frame" and ref.evidence_id == context.primary_frame_id:
                valid_refs.append(ref)

        obs_copy = MultimodalObservation.from_dict(obs.to_dict())
        obs_copy.evidence_refs = valid_refs

        # Hallucination Control: if model made claims with no verifiable evidence refs
        if not valid_refs:
            obs_copy.grounded = False
            obs_copy.confidence = min(obs_copy.confidence, 0.20)
            obs_copy.uncertainty_reason = "UNGROUNDED: Model claim references no verifiable evidence in context."
        else:
            obs_copy.grounded = True
            # Recompute supporting modalities from verified refs
            obs_copy.supporting_modalities = list(
                set([ref.modality for ref in valid_refs] + obs.supporting_modalities)
            )

        return obs_copy

    def _detect_cross_modal_conflicts(
        self,
        context: MultimodalContext,
        observations: list[MultimodalObservation],
    ) -> list[MultimodalObservation]:
        """Generate CROSS_MODAL_CONFLICT when different modalities disagree on state."""
        conflicts: list[MultimodalObservation] = []
        w = context.window

        # Conflict scenario 1: Spoken audio mentions an app or window title that conflicts with active window
        for seg in context.transcripts:
            spoken_lower = seg.text.lower()
            if w.active_application:
                app_lower = w.active_application.lower()
                # If speech explicitly claims a different well-known app name (e.g. "browser", "terminal", "finder")
                known_apps = {"chrome", "browser", "terminal", "finder", "textedit", "code", "ide"}
                spoken_app_mentions = [app for app in known_apps if app in spoken_lower]
                if spoken_app_mentions and not any(app in app_lower for app in spoken_app_mentions):
                    conflicts.append(
                        MultimodalObservation(
                            observation_id=f"obs_conflict_app_{seg.segment_id}_{w.window_id}",
                            session_id=w.session_id,
                            observation_type=ObservationType.CROSS_MODAL_CONFLICT,
                            description=(
                                f"Spoken instruction mentions '{', '.join(spoken_app_mentions)}' "
                                f"while active window is '{w.active_application}'."
                            ),
                            timestamp_ns=getattr(seg, "start_monotonic_ns", getattr(seg, "start_timestamp_ns", 0)),
                            relative_time_ms=round(
                                getattr(seg, "start_monotonic_ns", getattr(seg, "start_timestamp_ns", 0)) / 1_000_000.0, 2
                            ),
                            evidence_refs=[
                                MultimodalEvidenceRef(
                                    evidence_type="transcript_segment",
                                    evidence_id=seg.segment_id,
                                    modality=ModalityType.SPEECH_TRANSCRIPT.value,
                                    timestamp_ns=getattr(seg, "start_monotonic_ns", getattr(seg, "start_timestamp_ns", 0)),
                                    relative_time_ms=getattr(seg, "start_monotonic_ns", getattr(seg, "start_timestamp_ns", 0)) / 1_000_000.0,
                                )
                            ],
                            supporting_modalities=[ModalityType.SPEECH_TRANSCRIPT.value],
                            contradicting_modalities=[ModalityType.WINDOW_CONTEXT.value],
                            confidence=0.75,
                            uncertainty_reason="Discrepancy between spoken application reference and active OS window context.",
                            provider="deterministic",
                            model_id="cross_modal_fusion",
                            model_version="1.0.0",
                            fingerprint=f"conflict_app_{seg.segment_id}_{w.active_application}",
                            grounded=True,
                        )
                    )

        return conflicts
