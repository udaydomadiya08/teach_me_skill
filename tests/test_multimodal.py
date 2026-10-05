"""Comprehensive test suite for Phase 6: Local Multimodal Intelligence."""

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

import pytest

import pytest

from teach_a_skill.hardware.tiers import HardwareTier
from teach_a_skill.multimodal.benchmark import MultimodalBenchmarkRunner
from teach_a_skill.multimodal.cache import MultimodalCache
from teach_a_skill.multimodal.context import MultimodalContext, MultimodalContextBuilder
from teach_a_skill.multimodal.fusion import MultimodalFusionEngine
from teach_a_skill.multimodal.grounding import MultimodalGroundingEngine
from teach_a_skill.multimodal.models import (
    ModalityType,
    MultimodalEvidenceRef,
    MultimodalManifest,
    MultimodalObservation,
    ObservationType,
    TemporalWindow,
)
from teach_a_skill.multimodal.pipeline import MultimodalPipeline
from teach_a_skill.multimodal.providers.deterministic import DeterministicMultimodalProvider
from teach_a_skill.multimodal.providers.local_vlm import LocalVLMProvider
from teach_a_skill.multimodal.providers.mock import MockMultimodalProvider
from teach_a_skill.multimodal.providers.registry import MultimodalProviderRegistry
from teach_a_skill.multimodal.query import MultimodalQueryEngine
from teach_a_skill.multimodal.storage import MultimodalStorage
from teach_a_skill.multimodal.validator import MultimodalValidator
from teach_a_skill.perception.models import BoundingBox, TextRegion, UIElement, UIElementType
from teach_a_skill.representation.models import CanonicalEvent, CanonicalEventType, EventCategory
from teach_a_skill.storage.manager import StorageManager
from teach_a_skill.teaching.annotations.model import AnnotationType, TeachingAnnotation
from teach_a_skill.teaching.transcript.segment import TranscriptSegment


@pytest.fixture
def temp_storage():
    tmp_dir = Path(tempfile.mkdtemp(prefix="test_multimodal_"))
    sm = StorageManager(base_dir=tmp_dir)
    yield sm
    shutil.rmtree(tmp_dir, ignore_errors=True)


def make_box(x: float, y: float, w: float, h: float) -> BoundingBox:
    return BoundingBox(
        x=x,
        y=y,
        width=w,
        height=h,
        normalized_x=x / 1920.0,
        normalized_y=y / 1080.0,
        normalized_width=w / 1920.0,
        normalized_height=h / 1080.0,
        frame_width=1920,
        frame_height=1080,
    )


@pytest.fixture
def sample_context():
    win = TemporalWindow(
        window_id="win_0001_test",
        session_id="session_test",
        start_time_ms=1000.0,
        end_time_ms=3000.0,
        start_timestamp_ns=1_000_000_000,
        end_timestamp_ns=3_000_000_000,
        trigger_event_id="cevt_0001",
        active_application="TextEdit",
        active_window_title="Document 1",
        pointer_coordinates=(120.0, 150.0),
    )
    ev = CanonicalEvent(
        event_id="cevt_0001",
        source_event_id="raw_0001",
        timestamp="2026-10-04T12:00:00Z",
        monotonic_timestamp=100.0,
        relative_time_ms=1500.0,
        relative_time_ns=1_500_000_000,
        category=EventCategory.POINTER,
        canonical_event_type=CanonicalEventType.CLICK,
        raw_event_type="mouse_click",
        source="mouse",
        sequence=1,
        raw_x=120.0,
        raw_y=150.0,
        application="TextEdit",
        window_title="Document 1",
    )
    tr = TextRegion(
        region_id="tr_0001",
        frame_id="frame_0001",
        text="Save File",
        raw_text="Save File",
        normalized_text="save file",
        confidence=0.98,
        bbox=make_box(100.0, 140.0, 80.0, 30.0),
        reading_order=1,
    )
    el = UIElement(
        element_id="el_0001",
        frame_id="frame_0001",
        element_type=UIElementType.BUTTON_LIKE,
        bbox=make_box(95.0, 135.0, 90.0, 40.0),
        confidence=0.95,
        text_content="Save File",
        reading_order=1,
    )
    seg = TranscriptSegment(
        segment_id="seg_0001",
        teaching_session_id="session_test",
        sequence_number=1,
        start_monotonic_ns=1_200_000_000,
        end_monotonic_ns=2_200_000_000,
        start_wall_time="2026-10-04T12:00:01Z",
        end_wall_time="2026-10-04T12:00:02Z",
        text="Click on Save now",
        confidence=0.92,
    )
    ann = TeachingAnnotation(
        annotation_id="ann_0001",
        teaching_session_id="session_test",
        created_monotonic_ns=1_400_000_000,
        start_monotonic_ns=1_400_000_000,
        end_monotonic_ns=1_500_000_000,
        text="Important: save file before closing",
        type=AnnotationType.INSTRUCTION,
    )

    return MultimodalContext(
        window=win,
        events=[ev],
        ui_elements=[el],
        text_regions=[tr],
        transcripts=[seg],
        annotations=[ann],
        primary_frame_id="frame_0001",
        pointer_position=(120.0, 150.0),
    )


# -------------------------------------------------------------------------
# 1. UNIT TESTS: Models & Serialization
# -------------------------------------------------------------------------

def test_multimodal_observation_roundtrip():
    ref = MultimodalEvidenceRef(
        evidence_type="ocr_region",
        evidence_id="tr_001",
        modality=ModalityType.OCR_TEXT.value,
        timestamp_ns=1_000_000,
        relative_time_ms=1.0,
        bounding_box=make_box(10.0, 10.0, 50.0, 20.0),
    )
    obs = MultimodalObservation(
        observation_id="obs_001",
        session_id="sess_1",
        observation_type=ObservationType.VISIBLE_TEXT,
        description="Visible text 'Cancel' detected.",
        timestamp_ns=1_000_000,
        relative_time_ms=1.0,
        evidence_refs=[ref],
        supporting_modalities=[ModalityType.OCR_TEXT.value],
        confidence=0.95,
    )

    d = obs.to_dict()
    restored = MultimodalObservation.from_dict(d)
    assert restored.observation_id == "obs_001"
    assert restored.observation_type == ObservationType.VISIBLE_TEXT
    assert len(restored.evidence_refs) == 1
    assert restored.evidence_refs[0].evidence_id == "tr_001"
    assert restored.grounded is True


def test_temporal_window_roundtrip():
    win = TemporalWindow(
        window_id="win_01",
        session_id="sess_1",
        start_time_ms=0.0,
        end_time_ms=2000.0,
        start_timestamp_ns=0,
        end_timestamp_ns=2_000_000_000,
        trigger_event_id="cevt_1",
        canonical_event_ids=["cevt_1", "cevt_2"],
        active_application="Terminal",
    )
    d = win.to_dict()
    restored = TemporalWindow.from_dict(d)
    assert restored.window_id == "win_01"
    assert restored.active_application == "Terminal"
    assert len(restored.canonical_event_ids) == 2


# -------------------------------------------------------------------------
# 2. UNIT TESTS: Grounding Engine
# -------------------------------------------------------------------------

def test_grounding_engine_pointer_and_cooccurrence(sample_context):
    engine = MultimodalGroundingEngine(pointer_proximity_threshold_px=50.0)
    observations = engine.ground_context(sample_context)

    types = {o.observation_type for o in observations}
    assert ObservationType.APPLICATION_STATE in types
    assert ObservationType.POINTER_CLICK_TARGET in types
    assert ObservationType.CROSS_MODAL_MATCH in types
    assert ObservationType.ANNOTATION_PRESENT in types

    ptr_obs = next(o for o in observations if o.observation_type == ObservationType.POINTER_CLICK_TARGET)
    assert "Save File" in ptr_obs.description
    assert ModalityType.POINTER.value in ptr_obs.supporting_modalities
    assert ModalityType.UI_ELEMENT.value in ptr_obs.supporting_modalities
    assert ModalityType.OCR_TEXT.value in ptr_obs.supporting_modalities
    assert ptr_obs.grounded is True
    assert ptr_obs.confidence >= 0.90


def test_grounding_speech_lexical_overlap(sample_context):
    engine = MultimodalGroundingEngine()
    observations = engine.ground_context(sample_context)

    # Transcript has "Click on Save now", OCR has "Save File" -> word "save" matches
    speech_obs = next(o for o in observations if o.observation_type == ObservationType.CROSS_MODAL_MATCH)
    assert "Save" in speech_obs.description
    assert ModalityType.SPEECH_TRANSCRIPT.value in speech_obs.supporting_modalities
    assert ModalityType.OCR_TEXT.value in speech_obs.supporting_modalities


# -------------------------------------------------------------------------
# 3. UNIT TESTS: Multimodal Fusion & Hallucination Suppression
# -------------------------------------------------------------------------

def test_fusion_suppresses_hallucinations(sample_context):
    fusion = MultimodalFusionEngine()

    # Create a simulated hallucinated observation with zero valid evidence refs
    fake_obs = MultimodalObservation(
        observation_id="obs_fake",
        session_id="session_test",
        observation_type=ObservationType.VISIBLE_UI_ELEMENT,
        description="Imaginary search bar visible",
        timestamp_ns=1_000_000_000,
        relative_time_ms=1000.0,
        evidence_refs=[
            MultimodalEvidenceRef(
                evidence_type="ocr_region",
                evidence_id="non_existent_tr",
                modality=ModalityType.OCR_TEXT.value,
                timestamp_ns=100,
                relative_time_ms=0.1,
            )
        ],
        confidence=0.99,
        grounded=True,
    )

    fused = fusion.fuse(sample_context, [fake_obs])
    fake_res = next(o for o in fused if o.observation_id == "obs_fake")
    assert fake_res.grounded is False
    assert fake_res.confidence <= 0.20
    assert "UNGROUNDED" in (fake_res.uncertainty_reason or "")


def test_fusion_detects_cross_modal_conflict(sample_context):
    fusion = MultimodalFusionEngine()
    # Modify transcript to claim terminal while active app is TextEdit
    conflict_seg = TranscriptSegment(
        segment_id="seg_conflict",
        teaching_session_id="session_test",
        sequence_number=2,
        start_monotonic_ns=1_000_000_000,
        end_monotonic_ns=2_000_000_000,
        start_wall_time="2026-10-04T12:00:00Z",
        end_wall_time="2026-10-04T12:00:01Z",
        text="Open the terminal window right now",
    )
    sample_context.transcripts = [conflict_seg]

    fused = fusion.fuse(sample_context, [])
    conflicts = [o for o in fused if o.observation_type == ObservationType.CROSS_MODAL_CONFLICT]
    assert len(conflicts) >= 1
    assert "terminal" in conflicts[0].description
    assert ModalityType.WINDOW_CONTEXT.value in conflicts[0].contradicting_modalities


# -------------------------------------------------------------------------
# 4. MANDATORY SEMANTIC BOUNDARY TESTS (Phase 7+ Prohibition)
# -------------------------------------------------------------------------

def test_semantic_boundary_rejection_in_fusion(sample_context):
    """Prove Phase 6 fusion engine rejects Phase 7 intent / goal claims."""
    fusion = MultimodalFusionEngine()

    intent_obs = MultimodalObservation(
        observation_id="obs_intent",
        session_id="session_test",
        observation_type=ObservationType.VISIBLE_TEXT,
        description="The user's intent is to save the document and compile the project.",
        timestamp_ns=1_000_000_000,
        relative_time_ms=1000.0,
        evidence_refs=[],
    )

    fused = fusion.fuse(sample_context, [intent_obs])
    # Must be completely suppressed from fused results
    matching = [o for o in fused if o.observation_id == "obs_intent"]
    assert len(matching) == 0, "Intent claim was not suppressed by semantic boundary filter!"


def test_validator_detects_boundary_violations(temp_storage):
    """Prove MultimodalValidator flags and fails sessions with forbidden intent keywords."""
    session_id = "sess_boundary_viol"
    storage = MultimodalStorage(temp_storage, session_id)

    bad_obs = MultimodalObservation(
        observation_id="obs_bad_goal",
        session_id=session_id,
        observation_type=ObservationType.VISIBLE_TEXT,
        description="User wants to click save because the task goal is file backup.",
        timestamp_ns=1_000_000_000,
        relative_time_ms=1000.0,
        evidence_refs=[
            MultimodalEvidenceRef("canonical_event", "cevt_1", ModalityType.POINTER.value, 1000, 1.0)
        ],
        confidence=0.9,
    )
    manifest = MultimodalManifest("m1", session_id)
    storage.write_multimodal_artifacts([], [bad_obs], manifest)

    val = MultimodalValidator(temp_storage)
    report = val.validate_session(session_id)
    assert report["valid"] is False
    assert any("SEMANTIC BOUNDARY VIOLATION" in err for err in report["errors"])


# -------------------------------------------------------------------------
# 5. UNIT & INTEGRATION: Providers & Registry
# -------------------------------------------------------------------------

def test_provider_registry_hardware_selection():
    registry = MultimodalProviderRegistry(hardware_tier=HardwareTier.BASELINE)
    provider = registry.select_best_provider()
    assert isinstance(provider, DeterministicMultimodalProvider)
    assert provider.is_available()

    # Standard tier with no local weights still safely falls back
    reg_std = MultimodalProviderRegistry(hardware_tier=HardwareTier.STANDARD)
    p_std = reg_std.select_best_provider()
    assert isinstance(p_std, DeterministicMultimodalProvider)

    # Mock provider selectable when requested
    mock_p = reg_std.select_best_provider(preferred_provider="mock")
    assert isinstance(mock_p, MockMultimodalProvider)


def test_local_vlm_missing_weights_policy():
    """Verify LocalVLMProvider does NOT download weights and gracefully reports MODEL_UNAVAILABLE."""
    vlm = LocalVLMProvider(model_id="qwen2_vl", model_path=Path("/tmp/non_existent_weights"))
    assert vlm.is_available() is False
    health = vlm.health()
    assert health["available"] is False
    assert "MODEL_UNAVAILABLE" in health["load_error"]

    with pytest.raises(RuntimeError, match="MODEL_UNAVAILABLE"):
        vlm.analyze(None)  # type: ignore


# -------------------------------------------------------------------------
# 6. CACHE & CONTENT-ADDRESSED DETERMINISM
# -------------------------------------------------------------------------

def test_multimodal_cache_and_invalidation(temp_storage, sample_context):
    cache_dir = temp_storage.get_path("cache", "multimodal")
    cache = MultimodalCache(cache_dir)

    key1 = cache.compute_cache_key(
        sample_context, "deterministic", "rules", "1.0.0"
    )
    obs_list = [
        MultimodalObservation(
            observation_id="obs_cached_1",
            session_id="session_test",
            observation_type=ObservationType.VISIBLE_TEXT,
            description="Cached observation",
            timestamp_ns=1_000_000,
            relative_time_ms=1.0,
            confidence=0.9,
        )
    ]
    cache.put(key1, obs_list)

    cached = cache.get(key1)
    assert cached is not None
    assert len(cached) == 1
    assert cached[0].observation_id == "obs_cached_1"

    # Changing context pointer position invalidates cache key
    sample_context.pointer_position = (500.0, 500.0)
    key2 = cache.compute_cache_key(
        sample_context, "deterministic", "rules", "1.0.0"
    )
    assert key1 != key2
    assert cache.get(key2) is None


# -------------------------------------------------------------------------
# 7. STORAGE, INTEGRITY, RECOVERY
# -------------------------------------------------------------------------

def test_storage_atomic_write_and_recovery(temp_storage, sample_context):
    session_id = "session_storage_test"
    storage = MultimodalStorage(temp_storage, session_id)

    obs = MultimodalObservation(
        observation_id="obs_rec_1",
        session_id=session_id,
        observation_type=ObservationType.APPLICATION_STATE,
        description="App state active",
        timestamp_ns=1_000_000_000,
        relative_time_ms=1000.0,
        evidence_refs=[
            MultimodalEvidenceRef("canonical_event", "cevt_1", ModalityType.WINDOW_CONTEXT.value, 1000, 1.0)
        ],
    )
    manifest = MultimodalManifest("manifest_test", session_id)
    storage.write_multimodal_artifacts([sample_context.window], [obs], manifest)

    assert storage.exists() is True
    read_obs = storage.read_observations()
    assert len(read_obs) == 1
    assert read_obs[0].observation_id == "obs_rec_1"

    # Validate checksums
    val = MultimodalValidator(temp_storage)
    res = val.validate_session(session_id)
    assert res["valid"] is True
    assert len(res["errors"]) == 0


# -------------------------------------------------------------------------
# 8. QUERY ENGINE
# -------------------------------------------------------------------------

def test_multimodal_query_engine(temp_storage, sample_context):
    session_id = "session_query_test"
    storage = MultimodalStorage(temp_storage, session_id)

    grounding = MultimodalGroundingEngine()
    obs_list = grounding.ground_context(sample_context)
    manifest = MultimodalManifest("m1", session_id)
    storage.write_multimodal_artifacts([sample_context.window], obs_list, manifest)

    query = MultimodalQueryEngine(temp_storage, session_id)
    all_obs = query.get_all_observations()
    assert len(all_obs) > 0

    ptr_obs = query.get_pointer_interactions()
    assert len(ptr_obs) >= 1

    app_info = query.get_active_window_at(1500.0)
    assert app_info is not None
    assert app_info["application"] == "TextEdit"


# -------------------------------------------------------------------------
# 9. BENCHMARK RUNNER TEST
# -------------------------------------------------------------------------

def test_benchmark_runner_mock_and_deterministic(temp_storage, sample_context):
    # Setup session with canonical representation and multimodal artifacts
    session_id = "session_bench_test"
    storage = MultimodalStorage(temp_storage, session_id)
    manifest = MultimodalManifest("m_bench", session_id)
    storage.write_multimodal_artifacts([sample_context.window], [], manifest)

    runner = MultimodalBenchmarkRunner(temp_storage)
    # Testing runner with empty/synthetic session returns structured items
    items = runner.run_all(session_id)
    assert len(items) >= 1
    # Every item has valid peak RSS and result tag
    for it in items:
        assert it.peak_rss_mb > 0
        assert it.result in ("PASS", "NOT RUN", "SKIPPED")


# -------------------------------------------------------------------------
# 10. REAL DATA PIPELINE & PROVENANCE COMPLETENESS TEST
# -------------------------------------------------------------------------

def test_real_data_pipeline_and_provenance():
    """Verify multimodal pipeline on real recorded demonstration session_485fc80a."""
    from teach_a_skill.app import TeachSkillApp

    app = TeachSkillApp(quiet=True)
    app.initialize()

    pipe = MultimodalPipeline(app.storage_manager)
    manifest = pipe.process_session("session_485fc80a", force_rebuild=True)
    assert manifest.total_windows > 0
    assert manifest.total_observations > 0

    val = MultimodalValidator(app.storage_manager)
    report = val.validate_session("session_485fc80a")
    assert report["valid"] is True
    assert len(report["errors"]) == 0

    # Verify provenance completeness: every observation must trace to valid evidence
    query = MultimodalQueryEngine(app.storage_manager, "session_485fc80a")
    observations = query.get_all_observations()
    for obs in observations:
        assert obs.grounded is True
        assert len(obs.evidence_refs) > 0
        for ref in obs.evidence_refs:
            assert ref.evidence_id != ""
            assert ref.modality in [m.value for m in ModalityType]


# -------------------------------------------------------------------------
# 11. DETERMINISTIC REBUILD (BYTE IDENTICAL OBSERVATIONS)
# -------------------------------------------------------------------------

def test_deterministic_rebuild_identic(sample_context, temp_storage):
    """Verify that rebuilding from identical inputs produces identical observations."""
    session_id = "sess_rebuild_test"
    storage = MultimodalStorage(temp_storage, session_id)
    grounding = MultimodalGroundingEngine()

    obs1 = grounding.ground_context(sample_context)
    manifest1 = MultimodalManifest("m1", session_id)
    storage.write_multimodal_artifacts([sample_context.window], obs1, manifest1)
    checksums1 = json.loads((storage.multimodal_dir / "checksums.json").read_text())

    # Rebuild
    obs2 = grounding.ground_context(sample_context)
    manifest2 = MultimodalManifest("m1", session_id)
    storage.write_multimodal_artifacts([sample_context.window], obs2, manifest2)
    checksums2 = json.loads((storage.multimodal_dir / "checksums.json").read_text())

    assert checksums1["observations.jsonl"] == checksums2["observations.jsonl"]
    assert checksums1["windows.jsonl"] == checksums2["windows.jsonl"]


# -------------------------------------------------------------------------
# 12. HEALTH CHECK SUBSYSTEM VERIFICATION
# -------------------------------------------------------------------------

def test_multimodal_health_checks():
    """Verify that all Phase 6 health checks report healthy and pass."""
    from teach_a_skill.core.health import HealthChecker

    report = HealthChecker.run_health_check(full=True)
    assert report.healthy is True
    mm_checks = [c for c in report.checks if c.name.startswith("multimodal_")]
    assert len(mm_checks) == 6
    for c in mm_checks:
        assert c.passed is True


# -------------------------------------------------------------------------
# 13. CLI EXECUTION TEST
# -------------------------------------------------------------------------

def test_cli_multimodal_commands():
    """Verify Phase 6 CLI handlers run cleanly."""
    from teach_a_skill.app import TeachSkillApp
    from teach_a_skill.cli.main import cmd_multimodal

    app = TeachSkillApp(quiet=True)
    app.initialize()

    class Args:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    # 1. models
    ret = cmd_multimodal(app, Args(mm_action="models"), as_json=True)
    assert ret == 0

    # 2. health
    ret = cmd_multimodal(app, Args(mm_action="health"), as_json=True)
    assert ret == 0

    # 3. validate on real session
    ret = cmd_multimodal(app, Args(mm_action="validate", session="session_485fc80a"), as_json=True)
    assert ret == 0

    # 4. inspect on real session
    ret = cmd_multimodal(app, Args(mm_action="inspect", session="session_485fc80a", limit=10), as_json=True)
    assert ret == 0

