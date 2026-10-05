"""Deterministic rule-based semantic understanding provider."""

import hashlib
import re
from typing import Any, Optional

from teach_a_skill.core.logging import get_logger
from teach_a_skill.hardware.tiers import HardwareTier
from teach_a_skill.intent.models import (
    ActionType,
    DemonstratedIntent,
    DemonstrationUnderstanding,
    IntentType,
    Postcondition,
    Precondition,
    SemanticAction,
    StateTransition,
    StateTransitionType,
    TaskAmbiguity,
    TaskEntity,
    TaskStage,
)
from teach_a_skill.intent.providers.base import (
    SemanticCapabilities,
    SemanticProvider,
    SemanticProviderCategory,
)
from teach_a_skill.multimodal.models import MultimodalObservation, ObservationType

logger = get_logger("teach_a_skill.intent.providers.deterministic")

# Explicit intent matching rules based on validated keywords
INTENT_PATTERNS = {
    IntentType.SAVE_DOCUMENT: [
        r"\bsave\b",
        r"\bguardar\b",
        r"\bsave\s+as\b",
        r"\bexport\b",
        r"\bbackup\b",
    ],
    IntentType.OPEN_DOCUMENT: [
        r"\bopen\b",
        r"\babrir\b",
        r"\bload\b",
        r"\bopen\s+file\b",
    ],
    IntentType.EDIT_TEXT: [
        r"\btype\b",
        r"\bedit\b",
        r"\bwrite\b",
        r"\bmodify\b",
        r"\bupdate\b",
    ],
    IntentType.NAVIGATE_APPLICATION: [
        r"\bclick\b",
        r"\bnavigate\b",
        r"\bgoto\b",
        r"\bselect\b",
        r"\bbrowse\b",
    ],
    IntentType.SWITCH_WINDOW: [
        r"\bswitch\b",
        r"\bfocus\b",
        r"\bbring\s+to\s+front\b",
    ],
    IntentType.SEARCH_QUERY: [
        r"\bsearch\b",
        r"\bfind\b",
        r"\bquery\b",
        r"\blookup\b",
    ],
    IntentType.CLOSE_WINDOW: [
        r"\bclose\b",
        r"\bquit\b",
        r"\bexit\b",
    ],
}


class DeterministicSemanticProvider(SemanticProvider):
    """Deterministic, evidence-grounded semantic inference engine.
    
    Adheres strictly to the evidence hierarchy:
    1. Explicit teaching annotations (highest confidence).
    2. Spoken teaching transcripts.
    3. Grounded pointer interactions and UI elements co-occurrence.
    4. Observable window/application state transitions.
    
    Guaranteed 100% offline, zero network, runs on BASELINE hardware.
    """

    def __init__(self) -> None:
        self._capabilities = SemanticCapabilities(
            provider_id="deterministic",
            category=SemanticProviderCategory.DETERMINISTIC,
            supports_task_segmentation=True,
            supports_intent_inference=True,
            supports_ambiguity_detection=True,
            supported_hardware_tiers=[
                HardwareTier.BASELINE,
                HardwareTier.STANDARD,
                HardwareTier.HIGH,
            ],
            model_id="deterministic_semantic_engine",
            model_version="1.0.0",
        )

    @property
    def capabilities(self) -> SemanticCapabilities:
        return self._capabilities

    def is_available(self) -> bool:
        return True

    def infer(
        self,
        session_id: str,
        observations: list[MultimodalObservation],
        context_data: dict[str, Any],
    ) -> DemonstrationUnderstanding:
        """Derive structured task understanding from multimodal evidence."""
        transcripts = context_data.get("transcripts", [])
        annotations = context_data.get("annotations", [])
        canonical_events = context_data.get("canonical_events", [])

        # 1. Extract Entities (Applications, Windows, Buttons)
        entities_map: dict[str, TaskEntity] = {}
        for obs in observations:
            if obs.observation_type == ObservationType.APPLICATION_STATE:
                app_name = obs.description.split("'")[1] if "'" in obs.description else "Application"
                ent_id = f"ent_app_{app_name.lower().replace(' ', '_')}"
                if ent_id not in entities_map:
                    entities_map[ent_id] = TaskEntity(
                        entity_id=ent_id,
                        entity_type="application",
                        label=app_name,
                        evidence_refs=[r.to_dict() for r in obs.evidence_refs],
                    )

            for ref in obs.evidence_refs:
                if ref.evidence_type == "ui_element":
                    el_id = f"ent_ui_{ref.evidence_id}"
                    if el_id not in entities_map:
                        entities_map[el_id] = TaskEntity(
                            entity_id=el_id,
                            entity_type="ui_element",
                            label=ref.details.get("element_type", "UI_CONTROL"),
                            evidence_refs=[ref.to_dict()],
                        )
                elif ref.evidence_type == "ocr_region":
                    ocr_id = f"ent_text_{ref.evidence_id}"
                    if ocr_id not in entities_map:
                        entities_map[ocr_id] = TaskEntity(
                            entity_id=ocr_id,
                            entity_type="visible_text",
                            label=ref.details.get("text", "Text"),
                            evidence_refs=[ref.to_dict()],
                        )

        entities = list(entities_map.values())

        # 2. Extract Semantic Actions from Grounded Observations
        actions: list[SemanticAction] = []
        action_count = 1
        for obs in observations:
            if obs.observation_type in (
                ObservationType.POINTER_CLICK_TARGET,
                ObservationType.POINTER_PROXIMITY,
            ):
                target_ents = [
                    f"ent_ui_{r.evidence_id}"
                    for r in obs.evidence_refs
                    if r.evidence_type == "ui_element"
                ]
                text_ents = [
                    f"ent_text_{r.evidence_id}"
                    for r in obs.evidence_refs
                    if r.evidence_type == "ocr_region"
                ]
                act_type = (
                    ActionType.ACTIVATE_CONTROL
                    if obs.observation_type == ObservationType.POINTER_CLICK_TARGET
                    else ActionType.INSPECT_REGION
                )
                act_id = f"act_{action_count:04d}_{session_id}"
                actions.append(
                    SemanticAction(
                        action_id=act_id,
                        action_type=act_type,
                        description=f"User activated {obs.description}",
                        timestamp_ms=obs.relative_time_ms,
                        confidence=obs.confidence,
                        source_events=[
                            r.evidence_id
                            for r in obs.evidence_refs
                            if r.evidence_type == "canonical_event"
                        ],
                        target_entities=target_ents + text_ents,
                        state_effects=["Target control state updated."],
                        evidence_refs=[f"obs:{obs.observation_id}"],
                    )
                )
                action_count += 1

            elif obs.observation_type == ObservationType.APPLICATION_STATE:
                act_id = f"act_{action_count:04d}_{session_id}"
                actions.append(
                    SemanticAction(
                        action_id=act_id,
                        action_type=ActionType.SWITCH_APPLICATION,
                        description=obs.description,
                        timestamp_ms=obs.relative_time_ms,
                        confidence=obs.confidence,
                        source_events=[
                            r.evidence_id
                            for r in obs.evidence_refs
                            if r.evidence_type == "canonical_event"
                        ],
                        target_entities=[],
                        state_effects=["Application focus transitioned."],
                        evidence_refs=[f"obs:{obs.observation_id}"],
                    )
                )
                action_count += 1

        # 3. Derive Observable State Transitions
        state_transitions: list[StateTransition] = []
        for i in range(len(actions) - 1):
            a1 = actions[i]
            a2 = actions[i + 1]
            if a1.action_type == ActionType.SWITCH_APPLICATION:
                state_transitions.append(
                    StateTransition(
                        transition_id=f"trans_{i+1:04d}",
                        description=f"Focus shifted from prior state to {a2.description}",
                        before_state=a1.description,
                        after_state=a2.description,
                        transition_type=StateTransitionType.OBSERVED,
                        evidence_refs=a1.evidence_refs + a2.evidence_refs,
                    )
                )

        # 4. Infer Task Stages (Grouping actions into meaningful milestones)
        stages: list[TaskStage] = []
        if actions:
            # Stage segmentation based on temporal breaks or application switches
            stage_chunks: list[list[SemanticAction]] = []
            curr_chunk: list[SemanticAction] = []
            for act in actions:
                if curr_chunk and (
                    act.timestamp_ms - curr_chunk[-1].timestamp_ms > 3000.0
                    or act.action_type == ActionType.SWITCH_APPLICATION
                ):
                    stage_chunks.append(curr_chunk)
                    curr_chunk = [act]
                else:
                    curr_chunk.append(act)
            if curr_chunk:
                stage_chunks.append(curr_chunk)

            for s_idx, chunk in enumerate(stage_chunks, 1):
                s_id = f"stage_{s_idx:02d}_{session_id}"
                s_start = chunk[0].timestamp_ms
                s_end = chunk[-1].timestamp_ms
                names = [c.description for c in chunk[:2]]
                stages.append(
                    TaskStage(
                        stage_id=s_id,
                        name=f"Milestone {s_idx}: {chunk[0].action_type.value}",
                        description="; ".join(names),
                        start_time_ms=s_start,
                        end_time_ms=s_end,
                        confidence=0.90,
                        action_ids=[c.action_id for c in chunk],
                        evidence_refs=[ref for c in chunk for ref in c.evidence_refs],
                    )
                )

        # 5. Evidence-First Intent & Goal Inference
        # Hierarchy: 1. Annotations -> 2. Speech -> 3. Action / OCR evidence
        candidates: dict[IntentType, float] = {}
        candidate_sources: dict[IntentType, list[str]] = {}

        # Scan annotations (Weight = 1.0)
        for ann in annotations:
            text = ann.text.lower()
            for itype, patterns in INTENT_PATTERNS.items():
                if any(re.search(p, text) for p in patterns):
                    candidates[itype] = candidates.get(itype, 0.0) + 1.0
                    candidate_sources.setdefault(itype, []).append(f"annotation:{ann.annotation_id}")

        # Scan speech transcripts (Weight = 0.8)
        for seg in transcripts:
            text = seg.text.lower()
            for itype, patterns in INTENT_PATTERNS.items():
                if any(re.search(p, text) for p in patterns):
                    candidates[itype] = candidates.get(itype, 0.0) + 0.8
                    candidate_sources.setdefault(itype, []).append(f"transcript:{seg.segment_id}")

        # Scan visible OCR text in observations (Weight = 0.5)
        for obs in observations:
            text = obs.description.lower()
            for itype, patterns in INTENT_PATTERNS.items():
                if any(re.search(p, text) for p in patterns):
                    candidates[itype] = candidates.get(itype, 0.0) + 0.5
                    candidate_sources.setdefault(itype, []).append(f"observation:{obs.observation_id}")

        # Ambiguity resolution
        ambiguities: list[TaskAmbiguity] = []
        primary_intent_type = IntentType.CUSTOM_INTERACTION
        primary_confidence = 0.50
        alternatives: list[dict[str, Any]] = []

        if candidates:
            sorted_candidates = sorted(candidates.items(), key=lambda x: x[1], reverse=True)
            top_type, top_score = sorted_candidates[0]
            primary_intent_type = top_type
            primary_confidence = min(0.95, 0.60 + (top_score * 0.15))

            if len(sorted_candidates) > 1:
                second_type, second_score = sorted_candidates[1]
                # If score margin is narrow, register first-class ambiguity
                if top_score - second_score < 0.4:
                    amb_id = f"amb_0001_{session_id}"
                    ambiguities.append(
                        TaskAmbiguity(
                            ambiguity_id=amb_id,
                            description=f"Competing interpretations between {top_type} and {second_type}.",
                            interpretations=[
                                {"intent": str(top_type), "score": round(top_score, 2)},
                                {"intent": str(second_type), "score": round(second_score, 2)},
                            ],
                            reason="Multiple evidence signals with close weights detected.",
                            evidence_refs=candidate_sources.get(top_type, []) + candidate_sources.get(second_type, []),
                        )
                    )
                for alt_type, alt_score in sorted_candidates[1:]:
                    alternatives.append({"intent_type": str(alt_type), "score": round(alt_score, 2)})

        # Formulate goal description strictly based on inferred intent
        goal_descriptions = {
            IntentType.SAVE_DOCUMENT: "Persist document state and file changes to storage.",
            IntentType.OPEN_DOCUMENT: "Load external file or resource into active application.",
            IntentType.EDIT_TEXT: "Input or update text within target interface element.",
            IntentType.NAVIGATE_APPLICATION: "Navigate between views or application components.",
            IntentType.SWITCH_WINDOW: "Transition operating system focus between application windows.",
            IntentType.SEARCH_QUERY: "Execute lookup query to retrieve matching entries.",
            IntentType.FORM_SUBMISSION: "Submit completed input data to system handler.",
            IntentType.CLOSE_WINDOW: "Terminate active window session.",
            IntentType.CUSTOM_INTERACTION: "Execute demonstrated sequence of user interface operations.",
        }

        task_name = f"Demonstrated {primary_intent_type.value.replace('_', ' ').title()}"
        task_goal = goal_descriptions.get(primary_intent_type, "Accomplish demonstrated objective.")

        # Observable Preconditions and Postconditions
        preconditions = [
            Precondition(
                description=f"Application '{entities[0].label}' is running and available."
                if entities
                else "System desktop environment is ready.",
                observed=True,
            )
        ]
        postconditions = [
            Postcondition(
                description=f"Demonstration completed reaching {primary_intent_type.value} milestone.",
                observed=True,
            )
        ]

        # 6. Assemble DemonstratedIntent
        intent_obj = DemonstratedIntent(
            intent_id=f"intent_{session_id}",
            demonstration_id=session_id,
            intent_type=primary_intent_type,
            goal=task_goal,
            task_name=task_name,
            confidence=round(primary_confidence, 4),
            evidence_refs=[
                {"source": s} for s in candidate_sources.get(primary_intent_type, [])
            ],
            supporting_evidence=[
                {"source": s} for s in candidate_sources.get(primary_intent_type, [])
            ],
            contradicting_evidence=[],
            ambiguities=ambiguities,
            alternatives=alternatives,
            preconditions=preconditions,
            postconditions=postconditions,
            entities=entities,
            task_stages=[s.stage_id for s in stages],
            model_provider="deterministic",
            model_id="deterministic_semantic_engine",
            model_version="1.0.0",
            fingerprint=hashlib.sha256(f"{session_id}:{primary_intent_type}:{len(actions)}".encode()).hexdigest(),
        )

        return DemonstrationUnderstanding(
            task_id=f"task_{session_id}",
            session_id=session_id,
            task_name=task_name,
            description=f"Task consists of {len(stages)} stage(s) with {len(actions)} grounded action(s).",
            goal=task_goal,
            confidence=round(primary_confidence, 4),
            stages=stages,
            actions=actions,
            entities=entities,
            state_transitions=state_transitions,
            preconditions=preconditions,
            postconditions=postconditions,
            ambiguities=ambiguities,
            primary_intent=intent_obj,
            evidence_refs=[{"count": len(observations), "type": "multimodal_observations"}],
            metadata={
                "provider": "deterministic",
                "hardware_tier": str(HardwareTier.BASELINE),
                "total_actions": len(actions),
                "total_stages": len(stages),
            },
        )

    def health(self) -> dict[str, Any]:
        return {
            "status": "healthy",
            "provider_id": "deterministic",
            "available": True,
            "category": str(SemanticProviderCategory.DETERMINISTIC),
            "supports_hardware_baseline": True,
        }
