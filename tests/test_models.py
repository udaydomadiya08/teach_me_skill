"""Tests for model descriptor registry and budget compatibility."""

from teach_a_skill.hardware.budget import BudgetCalculator
from teach_a_skill.models.descriptor import Modality, ModelDescriptor
from teach_a_skill.models.registry import ModelRegistry


def test_registry_initialization():
    registry = ModelRegistry()
    models = registry.list_models()
    assert len(models) >= 5
    ids = {m.model_id for m in models}
    assert "cpu-ocr-compact" in ids
    assert "whisper-tiny-local" in ids
    assert "micro-vlm-0.5b" in ids


def test_registry_register_custom_model():
    registry = ModelRegistry()
    desc = ModelDescriptor(
        model_id="custom-fast-ocr",
        name="Custom Fast OCR",
        version="0.1.0",
        modality=[Modality.OCR],
        parameter_size="10M",
        quantization="int8",
        memory_requirement_mb=50,
        cpu_support=True,
        gpu_support=False,
        platform_support=["macos", "linux", "windows"],
    )
    registry.register(desc)
    assert registry.get("custom-fast-ocr") == desc


def test_filter_compatible_models_on_weak_cpu(weak_cpu_profile):
    registry = ModelRegistry()
    budget = BudgetCalculator.calculate(weak_cpu_profile)
    # Weak CPU has ~512MB-1024MB memory budget and no GPU
    compatible = registry.find_compatible_models(budget)
    compatible_ids = {m.model_id for m in compatible}

    # Small CPU models should fit
    assert "cpu-ocr-compact" in compatible_ids
    assert "whisper-tiny-local" in compatible_ids

    # Heavy models (3B and 7B VLMs) should exceed memory budget
    assert "standard-vlm-3b" not in compatible_ids
    assert "high-vlm-7b" not in compatible_ids


def test_filter_compatible_models_on_workstation(gpu_workstation_profile):
    registry = ModelRegistry()
    budget = BudgetCalculator.calculate(gpu_workstation_profile)
    compatible = registry.find_compatible_models(budget)
    compatible_ids = {m.model_id for m in compatible}

    # High workstation can fit all default reference models
    assert "high-vlm-7b" in compatible_ids
    assert "micro-vlm-0.5b" in compatible_ids


def test_modality_filtering(gpu_workstation_profile):
    registry = ModelRegistry()
    budget = BudgetCalculator.calculate(gpu_workstation_profile)
    ocr_models = registry.find_compatible_models(budget, modality=Modality.OCR)
    for m in ocr_models:
        assert Modality.OCR in m.modality
