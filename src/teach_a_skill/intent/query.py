"""Query API for accessing semantic intent, task decomposition, and grounded evidence lineage."""

from typing import Any, Optional

from teach_a_skill.intent.graph import TaskGraph
from teach_a_skill.intent.models import (
    DemonstratedIntent,
    DemonstrationUnderstanding,
    Postcondition,
    Precondition,
    SemanticAction,
    TaskAmbiguity,
    TaskEntity,
    TaskStage,
)
from teach_a_skill.intent.storage import IntentStorage
from teach_a_skill.storage.manager import StorageManager


class IntentQueryEngine:
    """Provides high-level programmatic access to Phase 7 semantic task understanding and lineage."""

    def __init__(self, storage_manager: StorageManager, session_id: str) -> None:
        self.storage_manager = storage_manager
        self.session_id = session_id
        self.storage = IntentStorage(storage_manager, session_id)
        self._understanding: Optional[DemonstrationUnderstanding] = None

    def _ensure_loaded(self) -> Optional[DemonstrationUnderstanding]:
        if self._understanding is None:
            tasks = self.storage.read_tasks()
            if tasks:
                self._understanding = tasks[0]
        return self._understanding

    def get_task(self) -> Optional[DemonstrationUnderstanding]:
        """Retrieve complete demonstration understanding object."""
        return self._ensure_loaded()

    def get_intent(self) -> Optional[DemonstratedIntent]:
        """Retrieve primary demonstrated intent."""
        u = self._ensure_loaded()
        if u and u.primary_intent:
            return u.primary_intent
        return self.storage.read_intent()

    def get_goals(self) -> list[dict[str, Any]]:
        """Retrieve demonstrated goal(s) and confidence."""
        u = self._ensure_loaded()
        if not u:
            return []
        goals = [{"goal": u.goal, "confidence": u.confidence, "task_name": u.task_name}]
        if u.primary_intent and u.primary_intent.alternatives:
            for alt in u.primary_intent.alternatives:
                goals.append(
                    {
                        "goal": alt.get("goal", ""),
                        "confidence": alt.get("confidence", 0.0),
                        "task_name": alt.get("intent_type", ""),
                        "is_alternative": True,
                    }
                )
        return goals

    def get_stages(self) -> list[TaskStage]:
        """Retrieve task stages ordered by start timestamp."""
        u = self._ensure_loaded()
        if u:
            return sorted(u.stages, key=lambda s: s.start_time_ms)
        return sorted(self.storage.read_stages(), key=lambda s: s.start_time_ms)

    def get_actions(self) -> list[SemanticAction]:
        """Retrieve semantic actions ordered by timestamp."""
        u = self._ensure_loaded()
        if u:
            return sorted(u.actions, key=lambda a: a.timestamp_ms)
        return sorted(self.storage.read_actions(), key=lambda a: a.timestamp_ms)

    def get_entities(self) -> list[TaskEntity]:
        """Retrieve all identified task entities."""
        u = self._ensure_loaded()
        if u:
            return u.entities
        return self.storage.read_entities()

    def get_preconditions(self) -> list[Precondition]:
        """Retrieve preconditions observed before task execution."""
        u = self._ensure_loaded()
        return u.preconditions if u else []

    def get_postconditions(self) -> list[Postcondition]:
        """Retrieve postconditions observed after task execution."""
        u = self._ensure_loaded()
        return u.postconditions if u else []

    def get_ambiguities(self) -> list[TaskAmbiguity]:
        """Retrieve documented task ambiguities and competing interpretations."""
        u = self._ensure_loaded()
        return u.ambiguities if u else []

    def get_task_graph(self) -> Optional[TaskGraph]:
        """Retrieve structured task graph."""
        u = self._ensure_loaded()
        if not u:
            return None
        if "task_graph" in u.metadata:
            return TaskGraph.from_dict(u.metadata["task_graph"])
        return TaskGraph.build_from_understanding(u)

    def get_evidence_for_claim(self, claim_id: str) -> list[dict[str, Any]]:
        """Trace any stage, action, entity, or intent ID back to its supporting evidence."""
        u = self._ensure_loaded()
        if not u:
            return []

        # Check Intent
        if u.primary_intent and u.primary_intent.intent_id == claim_id:
            return u.primary_intent.evidence_refs

        # Check Stages
        for stage in u.stages:
            if stage.stage_id == claim_id:
                return [{"evidence_ref": ref} for ref in stage.evidence_refs]

        # Check Actions
        for action in u.actions:
            if action.action_id == claim_id:
                return [
                    {"evidence_ref": ref, "source_events": action.source_events}
                    for ref in action.evidence_refs
                ]

        # Check Entities
        for ent in u.entities:
            if ent.entity_id == claim_id:
                return ent.evidence_refs

        # Check State Transitions
        for trans in u.state_transitions:
            if trans.transition_id == claim_id:
                return [{"evidence_ref": ref} for ref in trans.evidence_refs]

        return []
