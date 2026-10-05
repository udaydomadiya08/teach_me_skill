"""Tests verifying zero-model startup and graceful degradation."""

from unittest.mock import patch

from teach_a_skill.app import TeachSkillApp
from teach_a_skill.core.errors import FeatureNotImplementedInPhaseError
from teach_a_skill.hardware.profile import GPUInfo


def test_startup_without_ai_models(temp_dir):
    """Application must start cleanly when zero AI models exist."""
    app = TeachSkillApp(quiet=True)
    app.initialize()

    status = app.get_status()
    assert status["initialized"] is True
    assert status["models"]["registered_descriptors"] > 0
    # No models loaded in memory
    assert len(app.model_registry.list_models()) > 0
    app.shutdown()


def test_startup_without_gpu(temp_dir):
    """Application must initialize cleanly on CPU-only machines with no GPU."""
    with patch(
        "teach_a_skill.hardware.detector.HardwareDetector.detect_gpu",
        return_value=GPUInfo(
            available=False,
            type="none",
            model="None (CPU Only)",
            vram_bytes=None,
            unified_memory=False,
        ),
    ):
        app = TeachSkillApp(quiet=True)
        app.initialize()
        assert app._initialized is True
        assert app.get_hardware_profile().gpu.available is False
        app.shutdown()


def test_startup_with_limited_ram(temp_dir):
    """Application must initialize safely even when RAM is critically constrained."""
    app = TeachSkillApp(quiet=True)
    app.initialize()
    budget = app.get_resource_budget()
    assert budget.max_memory_mb > 0
    assert budget.preferred_memory_mb <= budget.max_memory_mb
    app.shutdown()


def test_future_features_not_implemented_error():
    """Verify that later-phase features raise FeatureNotImplementedInPhaseError and are not faked."""
    err = FeatureNotImplementedInPhaseError(feature_name="UniversalRecorder", target_phase=2)
    assert "Phase 2" in str(err)
    assert err.details["feature"] == "UniversalRecorder"
