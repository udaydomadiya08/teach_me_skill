"""Mock multimodal provider for synthetic testing, edge cases, and benchmarks."""

from typing import Any, Optional

from teach_a_skill.hardware.tiers import HardwareTier
from teach_a_skill.multimodal.context import MultimodalContext
from teach_a_skill.multimodal.models import (
    ModalityType,
    MultimodalEvidenceRef,
    MultimodalObservation,
    ObservationType,
)
from teach_a_skill.multimodal.providers.base import (
    LocalMultimodalProvider,
    ProviderCapabilities,
    ProviderCategory,
)


class MockMultimodalProvider(LocalMultimodalProvider):
    """Mock provider for unit tests, adversarial testing, and performance baselines.
    
    CRITICAL: Clearly classified as MOCK_PROVIDER. Never reported as a real model.
    """

    def __init__(
        self,
        provider_id: str = "mock_vlm",
        model_id: str = "mock_vision_language_v1",
        simulate_hallucinations: bool = False,
        simulate_conflict: bool = False,
        fixed_confidence: Optional[float] = None,
    ) -> None:
        self._provider_id = provider_id
        self._model_id = model_id
        self.simulate_hallucinations = simulate_hallucinations
        self.simulate_conflict = simulate_conflict
        self.fixed_confidence = fixed_confidence
        self._capabilities = ProviderCapabilities(
            provider_id=self._provider_id,
            category=ProviderCategory.MOCK,
            supports_vision=True,
            supports_text=True,
            supports_speech=True,
            supports_deterministic_sampling=True,
            max_context_elements=50,
            supported_hardware_tiers=[
                HardwareTier.BASELINE,
                HardwareTier.STANDARD,
                HardwareTier.HIGH,
            ],
            model_id=self._model_id,
            model_version="1.0.0-mock",
        )

    @property
    def capabilities(self) -> ProviderCapabilities:
        return self._capabilities

    def is_available(self) -> bool:
        return True

    def analyze(self, context: MultimodalContext) -> list[MultimodalObservation]:
        observations: list[MultimodalObservation] = []
        w = context.window
        conf = self.fixed_confidence if self.fixed_confidence is not None else 0.88

        # 1. Observed visible text observation
        if context.text_regions:
            first_tr = context.text_regions[0]
            evidence = [
                MultimodalEvidenceRef(
                    evidence_type="ocr_region",
                    evidence_id=first_tr.region_id,
                    modality=ModalityType.OCR_TEXT.value,
                    timestamp_ns=w.start_timestamp_ns,
                    relative_time_ms=w.start_time_ms,
                    bounding_box=first_tr.bbox,
                    details={"text": first_tr.text},
                )
            ]
            observations.append(
                MultimodalObservation(
                    observation_id=f"obs_mock_text_{w.window_id}",
                    session_id=w.session_id,
                    observation_type=ObservationType.VISIBLE_TEXT,
                    description=f"Mock model detected visible text label '{first_tr.text}'.",
                    timestamp_ns=w.start_timestamp_ns,
                    relative_time_ms=w.start_time_ms,
                    evidence_refs=evidence,
                    supporting_modalities=[ModalityType.OCR_TEXT.value, ModalityType.SCREEN_FRAME.value],
                    confidence=conf,
                    provider=self._provider_id,
                    model_id=self._model_id,
                    model_version="1.0.0-mock",
                    fingerprint=f"mock_text_{first_tr.region_id}",
                    grounded=True,
                )
            )

        # 2. Simulated ungrounded / hallucinated claim
        if self.simulate_hallucinations:
            observations.append(
                MultimodalObservation(
                    observation_id=f"obs_mock_halluc_{w.window_id}",
                    session_id=w.session_id,
                    observation_type=ObservationType.VISIBLE_UI_ELEMENT,
                    description="Detected imaginary button 'Submit Form' at non-existent location.",
                    timestamp_ns=w.start_timestamp_ns,
                    relative_time_ms=w.start_time_ms,
                    evidence_refs=[],  # No evidence!
                    supporting_modalities=[],
                    confidence=0.99,
                    provider=self._provider_id,
                    model_id=self._model_id,
                    model_version="1.0.0-mock",
                    fingerprint="mock_hallucination",
                    grounded=False,  # Un-grounded!
                )
            )

        # 3. Simulated cross-modal conflict
        if self.simulate_conflict and context.transcripts:
            seg = context.transcripts[0]
            observations.append(
                MultimodalObservation(
                    observation_id=f"obs_mock_conflict_{w.window_id}",
                    session_id=w.session_id,
                    observation_type=ObservationType.CROSS_MODAL_CONFLICT,
                    description=f"Spoken keyword '{seg.text}' contradicts active window '{w.active_application}'.",
                    timestamp_ns=w.start_timestamp_ns,
                    relative_time_ms=w.start_time_ms,
                    evidence_refs=[
                        MultimodalEvidenceRef(
                            evidence_type="transcript_segment",
                            evidence_id=seg.segment_id,
                            modality=ModalityType.SPEECH_TRANSCRIPT.value,
                            timestamp_ns=seg.start_timestamp_ns,
                            relative_time_ms=seg.start_timestamp_ns / 1_000_000.0,
                        )
                    ],
                    supporting_modalities=[ModalityType.SPEECH_TRANSCRIPT.value],
                    contradicting_modalities=[ModalityType.WINDOW_CONTEXT.value],
                    confidence=0.75,
                    uncertainty_reason="Voice transcript refers to an application not currently in focus.",
                    provider=self._provider_id,
                    model_id=self._model_id,
                    model_version="1.0.0-mock",
                    fingerprint=f"mock_conflict_{seg.segment_id}",
                    grounded=True,
                )
            )

        return observations

    def health(self) -> dict[str, Any]:
        return {
            "status": "healthy",
            "provider_id": self._provider_id,
            "category": str(ProviderCategory.MOCK),
            "available": True,
            "is_mock": True,
        }

    def estimate_cost(self, context: MultimodalContext) -> dict[str, Any]:
        return {
            "estimated_memory_mb": 1.0,
            "estimated_latency_ms": 5.0,
            "requires_gpu": False,
        }
