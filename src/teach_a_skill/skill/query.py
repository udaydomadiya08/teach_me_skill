"""High-level query API and explainability engine for compiled skills."""

from typing import Any, Optional

from teach_a_skill.skill.models import (
    SkillCheckpoint,
    SkillDependency,
    SkillIR,
    SkillParameter,
    SkillPostcondition,
    SkillPrecondition,
    SkillStep,
    SkillVariable,
)
from teach_a_skill.skill.storage import SkillStorage
from teach_a_skill.storage.manager import StorageManager


class SkillQueryEngine:
    """Provides high-level programmatic access to Skill IR and compilation explainability."""

    def __init__(self, storage_manager: StorageManager, session_id: str) -> None:
        self.storage_manager = storage_manager
        self.session_id = session_id
        self.storage = SkillStorage(storage_manager, session_id)
        self._skill: Optional[SkillIR] = None

    def _ensure_loaded(self) -> Optional[SkillIR]:
        if self._skill is None:
            self._skill = self.storage.read_skill()
        return self._skill

    def get_skill(self) -> Optional[SkillIR]:
        """Retrieve complete Skill IR object."""
        return self._ensure_loaded()

    def get_skill_status(self) -> Optional[str]:
        """Retrieve compilation status."""
        s = self._ensure_loaded()
        return str(s.status) if s else None

    def get_parameters(self) -> list[SkillParameter]:
        """Retrieve extracted parameters."""
        s = self._ensure_loaded()
        if s:
            return s.parameters
        return self.storage.read_parameters()

    def get_variables(self) -> list[SkillVariable]:
        """Retrieve semantic state variables."""
        s = self._ensure_loaded()
        if s:
            return s.variables
        return self.storage.read_variables()

    def get_steps(self) -> list[SkillStep]:
        """Retrieve ordered skill steps."""
        s = self._ensure_loaded()
        if s:
            return s.steps
        return self.storage.read_steps()

    def get_checkpoints(self) -> list[SkillCheckpoint]:
        """Retrieve verification checkpoints."""
        s = self._ensure_loaded()
        if s:
            return s.checkpoints
        return self.storage.read_checkpoints()

    def get_dependencies(self) -> list[SkillDependency]:
        """Retrieve environmental dependencies."""
        s = self._ensure_loaded()
        if s:
            return s.dependencies
        return self.storage.read_dependencies()

    def get_preconditions(self) -> list[SkillPrecondition]:
        """Retrieve compiled preconditions."""
        s = self._ensure_loaded()
        return s.preconditions if s else []

    def get_postconditions(self) -> list[SkillPostcondition]:
        """Retrieve compiled postconditions."""
        s = self._ensure_loaded()
        return s.postconditions if s else []

    def get_provenance(self) -> dict[str, Any]:
        """Retrieve compilation provenance ledger."""
        s = self._ensure_loaded()
        return s.provenance if s else {}

    def get_warnings(self) -> list[str]:
        """Retrieve compilation warnings if any."""
        s = self._ensure_loaded()
        warnings = []
        if s:
            if s.ambiguities:
                warnings.append(f"Skill requires disambiguation: {len(s.ambiguities)} ambiguity record(s).")
            if s.confidence < 0.70:
                warnings.append(f"Low overall demonstration confidence: {s.confidence:.2f}")
        return warnings

    def get_fingerprint(self) -> str:
        """Retrieve canonical SHA-256 fingerprint."""
        s = self._ensure_loaded()
        return s.fingerprint if s else ""

    def explain_compilation(self) -> dict[str, Any]:
        """Generate human-readable explanation of how demonstration semantics became Skill IR."""
        s = self._ensure_loaded()
        if not s:
            return {"error": "Skill not found"}

        explanation = {
            "skill_id": s.skill_id,
            "name": s.name,
            "goal": s.goal,
            "status": str(s.status),
            "step_explanations": [],
            "parameter_explanations": self.explain_parameters(),
            "dependency_explanations": [],
        }

        for step in s.steps:
            explanation["step_explanations"].append(
                {
                    "step_id": step.step_id,
                    "ordinal": step.ordinal,
                    "action_type": str(step.action_type),
                    "target": step.target,
                    "source_semantic_action": step.source_semantic_action_id,
                    "evidence_grounding": (
                        step.grounding.preferred_strategy.value if step.grounding else "NONE"
                    ),
                    "verification": (
                        step.verification.expected_state if step.verification else "NONE"
                    ),
                }
            )

        for dep in s.dependencies:
            explanation["dependency_explanations"].append(
                {
                    "dependency_id": dep.dependency_id,
                    "type": dep.dependency_type,
                    "name": dep.name,
                    "reason": dep.description,
                }
            )

        return explanation

    def explain_parameters(self) -> list[dict[str, Any]]:
        """Explain parameter vs constant classification rationale."""
        s = self._ensure_loaded()
        if not s:
            return []

        explanations = []
        for p in s.parameters:
            explanations.append(
                {
                    "parameter": p.name,
                    "type": str(p.type),
                    "classification": str(p.classification),
                    "example_value": p.example_value,
                    "confidence": p.confidence,
                    "reason": (
                        f"Demonstrated value '{p.example_value}' identified as variable input parameter."
                        if p.classification == "PARAMETER"
                        else "Value classified as constant or environmental target."
                    ),
                }
            )
        return explanations
