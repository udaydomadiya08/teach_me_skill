"""Mock semantic provider for synthetic testing, edge cases, and benchmarks."""

from typing import Any, Optional

from teach_a_skill.hardware.tiers import HardwareTier
from teach_a_skill.intent.models import (
    ActionType,
    DemonstratedIntent,
    DemonstrationUnderstanding,
    IntentType,
    Postcondition,
    Precondition,
    SemanticAction,
    TaskAmbiguity,
    TaskEntity,
    TaskStage,
)
from teach_a_skill.intent.providers.base import (
    SemanticCapabilities,
    SemanticProvider,
    SemanticProviderCategory,
)
from teach_a_skill.multimodal.models import MultimodalObservation


class MockSemanticProvider(SemanticProvider):
    """Mock provider for unit tests, ambiguity simulations, and prompt injection defense."""

    def __init__(
        self,
        provider_id: str = "mock_llm",
        model_id: str = "mock_semantic_model_v1",
        forced_intent_type: Optional[IntentType] = None,
        simulate_ambiguity: bool = False,
        simulate_unsupported_claims: bool = False,
    ) -> None:
        self._provider_id = provider_id
        self._model_id = model_id
        self.forced_intent_type = forced_intent_type
        self.simulate_ambiguity = simulate_ambiguity
        self.simulate_unsupported_claims = simulate_unsupported_claims

        self._capabilities = SemanticCapabilities(
            provider_id=self._provider_id,
            category=SemanticProviderCategory.MOCK,
            supports_task_segmentation=True,
            supports_intent_inference=True,
            supports_ambiguity_detection=True,
            supported_hardware_tiers=[
                HardwareTier.BASELINE,
                HardwareTier.STANDARD,
                HardwareTier.HIGH,
            ],
            model_id=self._model_id,
            model_version="1.0.0-mock",
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
        itype = self.forced_intent_type or IntentType.SAVE_DOCUMENT
        conf = 0.88

        # Entities
        ent = TaskEntity(
            entity_id=f"ent_mock_{session_id}",
            entity_type="application",
            label="MockApp",
            evidence_refs=[{"source": "mock"}],
        )

        # Actions
        act = SemanticAction(
            action_id=f"act_mock_001_{session_id}",
            action_type=ActionType.ACTIVATE_CONTROL,
            description="Mock activation of save trigger",
            timestamp_ms=100.0,
            confidence=conf,
            source_events=["cevt_mock_01"],
            target_entities=[ent.entity_id],
            state_effects=["State preserved"],
            evidence_refs=["mock_ref_1"] if not self.simulate_unsupported_claims else [],
        )

        # Stage
        stg = TaskStage(
            stage_id=f"stage_mock_01_{session_id}",
            name="Mock Primary Stage",
            description="Executing mock demonstrated action",
            start_time_ms=0.0,
            end_time_ms=200.0,
            confidence=conf,
            action_ids=[act.action_id],
            evidence_refs=["mock_ref_1"] if not self.simulate_unsupported_claims else [],
        )

        ambiguities = []
        if self.simulate_ambiguity:
            ambiguities.append(
                TaskAmbiguity(
                    ambiguity_id=f"amb_mock_{session_id}",
                    description="Simulated ambiguity between Save and Export",
                    interpretations=[
                        {"intent": "SAVE_DOCUMENT", "score": 0.52},
                        {"intent": "EXPORT_FILE", "score": 0.48},
                    ],
                    reason="Synthetic ambiguity test scenario.",
                    evidence_refs=["ev_amb_1"],
                )
            )

        intent_obj = DemonstratedIntent(
            intent_id=f"intent_mock_{session_id}",
            demonstration_id=session_id,
            intent_type=itype,
            goal="Mock task objective execution",
            task_name=f"Mock {itype.value}",
            confidence=conf,
            evidence_refs=[{"mock": True}] if not self.simulate_unsupported_claims else [],
            ambiguities=ambiguities,
            entities=[ent],
            task_stages=[stg.stage_id],
            model_provider=self._provider_id,
            model_id=self._model_id,
            model_version="1.0.0-mock",
            fingerprint="mock_fingerprint",
        )

        return DemonstrationUnderstanding(
            task_id=f"task_mock_{session_id}",
            session_id=session_id,
            task_name=f"Mock {itype.value}",
            description="Mock demonstration analysis result.",
            goal="Mock task objective execution",
            confidence=conf,
            stages=[stg],
            actions=[act],
            entities=[ent],
            ambiguities=ambiguities,
            primary_intent=intent_obj,
            evidence_refs=[{"mock": True}] if not self.simulate_unsupported_claims else [],
            metadata={"is_mock": True},
        )

    def health(self) -> dict[str, Any]:
        return {
            "status": "healthy",
            "provider_id": self._provider_id,
            "category": str(SemanticProviderCategory.MOCK),
            "available": True,
            "is_mock": True,
        }
