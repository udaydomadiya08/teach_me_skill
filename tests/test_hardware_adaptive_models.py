"""Comprehensive unit and integration test suite for Phase 12 Hardware-Adaptive Model System."""

import time
import pytest

from teach_a_skill.hardware.capability import CapabilityMatrix, CapabilityProfile, SupportLevel
from teach_a_skill.hardware.detector import HardwareDetector
from teach_a_skill.hardware.profile import (
    CPUInfo,
    GPUInfo,
    HardwareProfile,
    MemoryInfo,
    StorageInfo,
)
from teach_a_skill.models.budget import ModelResourceBudget
from teach_a_skill.models.cache import ModelCache
from teach_a_skill.models.descriptor import Modality, ModelDescriptor
from teach_a_skill.models.fallback import FallbackManager
from teach_a_skill.models.integrity import ModelIntegrityVerifier
from teach_a_skill.models.lifecycle import ModelLifecycleManager
from teach_a_skill.models.monitor import ResourceMonitor
from teach_a_skill.models.providers.base import ModelProvider
from teach_a_skill.models.providers.deterministic import DeterministicProvider
from teach_a_skill.models.providers.test_model import TestModelProvider
from teach_a_skill.models.registry import ModelRegistry
from teach_a_skill.models.router import TaskRouter, UntrustedOutputViolationError
from teach_a_skill.models.scheduler import (
    CancellationToken,
    InferenceCancelledError,
    InferenceQueueFullError,
    InferenceScheduler,
    InferenceTimeoutError,
)
from teach_a_skill.models.selector import ModelSelector, RejectionReason
from teach_a_skill.models.spec import (
    DownloadPolicy,
    LifecycleState,
    ModelArtifact,
    ModelSpec,
    TaskRequirements,
    TaskType,
)
from teach_a_skill.models.validator import ModelSafetyValidator


@pytest.fixture
def mock_baseline_profile() -> HardwareProfile:
    return HardwareProfile(
        platform="macos",
        os_version="14.0",
        architecture="arm64",
        cpu=CPUInfo(architecture="arm64", vendor="Apple", model="Apple M1", logical_cores=8, physical_cores=8),
        memory=MemoryInfo(total_bytes=8 * 1024**3, available_bytes=2 * 1024**3),
        gpu=GPUInfo(available=True, type="apple_silicon", model="Apple M1 GPU", unified_memory=True),
        accelerators=["apple_silicon"],
        storage=StorageInfo(target_path="/tmp", total_bytes=256 * 1024**3, free_bytes=100 * 1024**3),
        capability_class="BASELINE",
        metal_available=True,
    )


@pytest.fixture
def mock_workstation_profile() -> HardwareProfile:
    return HardwareProfile(
        platform="linux",
        os_version="Ubuntu 22.04",
        architecture="x86_64",
        cpu=CPUInfo(architecture="x86_64", vendor="Intel", model="Intel Xeon", logical_cores=32, physical_cores=16),
        memory=MemoryInfo(total_bytes=64 * 1024**3, available_bytes=48 * 1024**3),
        gpu=GPUInfo(available=True, type="nvidia_cuda", model="NVIDIA A100", vram_bytes=80 * 1024**3),
        accelerators=["nvidia_cuda"],
        storage=StorageInfo(target_path="/tmp", total_bytes=2000 * 1024**3, free_bytes=1500 * 1024**3),
        capability_class="HIGH",
        cuda_available=True,
    )


# --- 1. HARDWARE CAPABILITY MATRIX ---

def test_hardware_capability_matrix_baseline(mock_baseline_profile):
    cap = CapabilityMatrix.evaluate(mock_baseline_profile)
    assert cap.tier.value == "BASELINE"
    assert cap.is_task_supported("ocr")
    assert cap.is_task_supported("stt")
    assert cap.get_support_level("large_vlm") == SupportLevel.UNSUPPORTED
    assert cap.recommended_concurrency == 1


def test_hardware_capability_matrix_high(mock_workstation_profile):
    cap = CapabilityMatrix.evaluate(mock_workstation_profile)
    assert cap.tier.value == "HIGH"
    assert cap.is_task_supported("large_vlm")
    assert cap.recommended_concurrency == 4


# --- 2. MODEL REGISTRY & PROVENANCE ---

def test_model_registry_crud():
    registry = ModelRegistry()
    assert len(registry.list()) >= 5
    assert registry.get_spec("cpu-ocr-compact") is not None

    custom_spec = ModelSpec(
        model_id="custom-nlp-model",
        name="Custom Fast NLP",
        version="1.0.0",
        provider="custom.nlp",
        task_types=[TaskType.TEXT_CLASSIFICATION],
        parameter_count="15M",
        quantization="int8",
        precision="int8",
        estimated_ram_mb=60,
        estimated_vram_mb=0,
        disk_size_mb=40,
        context_length=1024,
        latency_estimate_ms=25.0,
        license="Apache-2.0",
        source="builtin",
        checksum="custom-nlp-chk-1",
        artifact_format="builtin",
    )
    registry.register(custom_spec)
    assert registry.get_spec("custom-nlp-model") == custom_spec
    assert registry.fingerprint("custom-nlp-model") is not None

    # Search
    search_res = registry.search("custom")
    assert any(s.model_id == "custom-nlp-model" for s in search_res)

    # Unregister
    removed = registry.unregister("custom-nlp-model")
    assert removed
    assert registry.get_spec("custom-nlp-model") is None


def test_model_registry_legacy_descriptor_compat():
    registry = ModelRegistry()
    legacy_desc = ModelDescriptor(
        model_id="legacy-ocr-tool",
        name="Legacy OCR Tool",
        version="0.9.0",
        modality=[Modality.OCR],
        parameter_size="10M",
        quantization="int8",
        memory_requirement_mb=45,
        cpu_support=True,
        gpu_support=False,
        platform_support=["macos", "linux"],
    )
    registry.register(legacy_desc)
    assert registry.get("legacy-ocr-tool") is not None
    spec = registry.get_spec("legacy-ocr-tool")
    assert spec is not None
    assert TaskType.OCR in spec.task_types


# --- 3. INTEGRITY & SECURITY VERIFICATION ---

def test_model_integrity_verifier_success():
    spec = ModelSpec(
        model_id="valid-model",
        name="Valid Model",
        version="1.0.0",
        provider="test",
        task_types=[TaskType.TEXT_CLASSIFICATION],
        parameter_count="5M",
        quantization="int8",
        precision="int8",
        estimated_ram_mb=30,
        estimated_vram_mb=0,
        disk_size_mb=20,
        context_length=512,
        latency_estimate_ms=10.0,
        artifact_format="builtin",
        trust_level="TRUSTED",
    )
    res = ModelIntegrityVerifier.verify_spec(spec)
    assert res.passed


def test_model_integrity_verifier_path_traversal():
    spec = ModelSpec(
        model_id="malicious-model",
        name="Malicious Model",
        version="1.0.0",
        provider="test",
        task_types=[TaskType.TEXT_CLASSIFICATION],
        parameter_count="5M",
        quantization="int8",
        precision="int8",
        estimated_ram_mb=30,
        estimated_vram_mb=0,
        disk_size_mb=20,
        context_length=512,
        latency_estimate_ms=10.0,
        source="../../etc/passwd",
        artifact_format="builtin",
    )
    res = ModelIntegrityVerifier.verify_spec(spec)
    assert not res.passed
    assert "path traversal" in res.reason.lower()


def test_model_integrity_verifier_untrusted_trust_level():
    spec = ModelSpec(
        model_id="untrusted-model",
        name="Untrusted Model",
        version="1.0.0",
        provider="test",
        task_types=[TaskType.TEXT_CLASSIFICATION],
        parameter_count="5M",
        quantization="int8",
        precision="int8",
        estimated_ram_mb=30,
        estimated_vram_mb=0,
        disk_size_mb=20,
        context_length=512,
        latency_estimate_ms=10.0,
        trust_level="UNTRUSTED",
        artifact_format="builtin",
    )
    res = ModelIntegrityVerifier.verify_spec(spec)
    assert not res.passed
    assert "rejected by safety policy" in res.reason


# --- 4. DETERMINISTIC MODEL SELECTION ---

def test_model_selector_cheapest_capable(mock_baseline_profile):
    registry = ModelRegistry()
    candidates = registry.list()
    budget = ModelResourceBudget.from_hardware(mock_baseline_profile)
    req = TaskRequirements(task_type=TaskType.OCR)

    sel = ModelSelector.select_model(candidates, req, budget, mock_baseline_profile)
    assert sel.is_successful
    assert sel.selected_model.model_id in ("deterministic-engine", "cpu-ocr-compact")


def test_model_selector_memory_rejection(mock_baseline_profile):
    registry = ModelRegistry()
    candidates = registry.list()
    # Extreme tight budget: 10MB RAM max (all candidates including deterministic-engine (16MB) exceed)
    tight_budget = ModelResourceBudget(max_ram_mb=10)
    req = TaskRequirements(task_type=TaskType.MULTIMODAL_GROUNDING)

    sel = ModelSelector.select_model(candidates, req, tight_budget, mock_baseline_profile)
    assert not sel.is_successful
    assert "standard-vlm-3b" in sel.rejection_reasons
    assert RejectionReason.INSUFFICIENT_RAM.value in sel.rejection_reasons["standard-vlm-3b"]


# --- 5. MODEL LIFECYCLE & MEMORY EVICTION ---

def test_model_lifecycle_flow():
    mgr = ModelLifecycleManager()
    budget = ModelResourceBudget(max_ram_mb=256, max_loaded_models=2)
    provider1 = TestModelProvider(simulated_ram_mb=64)
    mgr.register_provider(provider1)

    assert provider1.state == LifecycleState.REGISTERED
    loaded = mgr.load_model(provider1.model_id, budget)
    assert loaded
    assert provider1.state == LifecycleState.READY

    # Inference lock
    locked = mgr.acquire_inference_lock(provider1.model_id)
    assert locked
    assert provider1.state == LifecycleState.BUSY

    # Unload while busy must fail
    unloaded = mgr.unload_model(provider1.model_id)
    assert not unloaded
    assert provider1.state == LifecycleState.BUSY

    mgr.release_inference_lock(provider1.model_id)
    assert provider1.state == LifecycleState.READY

    unloaded = mgr.unload_model(provider1.model_id)
    assert unloaded
    assert provider1.state == LifecycleState.IDLE


# --- 6. MODEL CACHE & INTEGRITY ---

def test_model_cache_hit_and_integrity():
    cache = ModelCache(max_entries=10)
    mfp = "model-fp-1"
    ifp = "input-fp-1"
    cfg = {"temp": 0.0}

    key = cache.put(mfp, ifp, cfg, "v1", {"result": "success"})
    assert cache.size() == 1

    # Cache hit
    val = cache.get(key, expected_model_fingerprint=mfp)
    assert val == {"result": "success"}

    # Model fingerprint mismatch returns None
    val_mismatch = cache.get(key, expected_model_fingerprint="different-model")
    assert val_mismatch is None

    # Cache stats
    stats = cache.stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1


# --- 7. INFERENCE SCHEDULER & CONCURRENCY ---

def test_scheduler_timeout():
    sched = InferenceScheduler(max_concurrency=1)

    def slow_fn():
        time.sleep(0.1)
        return "done"

    with pytest.raises(InferenceTimeoutError):
        sched.execute(slow_fn, timeout_seconds=0.01)

    sched.shutdown()


def test_scheduler_cancellation():
    sched = InferenceScheduler(max_concurrency=1)
    tok = CancellationToken()
    tok.cancel()

    def dummy():
        return "ok"

    with pytest.raises(InferenceCancelledError):
        sched.execute(dummy, cancellation_token=tok)

    sched.shutdown()


# --- 8. FALLBACK & TASK ROUTER ---

def test_task_router_deterministic_execution(mock_baseline_profile):
    router = TaskRouter(hardware_profile=mock_baseline_profile)
    req = TaskRequirements(task_type=TaskType.TEXT_CLASSIFICATION)
    res = router.route_and_execute(req, inputs="click the submit button")

    assert res.task_type == TaskType.TEXT_CLASSIFICATION
    assert res.confidence > 0.0
    assert not res.fallback_used
    assert not res.cache_hit

    # Re-executing identical request hits cache
    res_cached = router.route_and_execute(req, inputs="click the submit button")
    assert res_cached.cache_hit
    assert res_cached.output == res.output


def test_task_router_untrusted_output_boundary(mock_baseline_profile):
    router = TaskRouter(hardware_profile=mock_baseline_profile)

    # Injected dangerous token in output must be rejected
    with pytest.raises(UntrustedOutputViolationError):
        router._validate_untrusted_output("Result: rm -rf /etc/data")


# --- 9. SAFETY & ZERO-NETWORK VALIDATOR ---

def test_model_safety_validator():
    spec = ModelSpec(
        model_id="clean-spec",
        name="Clean Spec",
        version="1.0.0",
        provider="test",
        task_types=[TaskType.TEXT_CLASSIFICATION],
        parameter_count="1M",
        quantization="none",
        precision="int8",
        estimated_ram_mb=10,
        estimated_vram_mb=0,
        disk_size_mb=5,
        context_length=256,
        latency_estimate_ms=5.0,
        local_only=True,
        source="builtin",
        artifact_format="builtin",
    )
    ok, _ = ModelSafetyValidator.validate_spec_safety(spec)
    assert ok

    net_ok, _ = ModelSafetyValidator.validate_network_isolation(spec)
    assert net_ok

    out_ok, _ = ModelSafetyValidator.validate_output_safety("Hello safe output")
    assert out_ok

    out_bad, msg = ModelSafetyValidator.validate_output_safety("malicious sudo rm -rf /")
    assert not out_bad
    assert "sudo " in msg or "rm -rf" in msg

