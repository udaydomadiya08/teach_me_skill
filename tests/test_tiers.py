"""Tests for hardware capability tier classification."""

from teach_a_skill.hardware.profile import CPUInfo, GPUInfo, MemoryInfo
from teach_a_skill.hardware.tiers import HardwareTier, TierClassifier


def test_classify_weak_cpu(weak_cpu_profile):
    """Very weak CPU-only machine must be classified as BASELINE."""
    tier = TierClassifier.classify(
        cpu=weak_cpu_profile.cpu,
        memory=weak_cpu_profile.memory,
        gpu=weak_cpu_profile.gpu,
        accelerators=weak_cpu_profile.accelerators,
    )
    assert tier == HardwareTier.BASELINE


def test_classify_8gb_laptop(laptop_8gb_profile):
    """8GB budget laptop must be classified as BASELINE."""
    tier = TierClassifier.classify(
        cpu=laptop_8gb_profile.cpu,
        memory=laptop_8gb_profile.memory,
        gpu=laptop_8gb_profile.gpu,
        accelerators=laptop_8gb_profile.accelerators,
    )
    assert tier == HardwareTier.BASELINE


def test_classify_16gb_laptop(laptop_16gb_profile):
    """16GB multi-core laptop with plenty of free RAM is classified as STANDARD."""
    tier = TierClassifier.classify(
        cpu=laptop_16gb_profile.cpu,
        memory=laptop_16gb_profile.memory,
        gpu=laptop_16gb_profile.gpu,
        accelerators=laptop_16gb_profile.accelerators,
    )
    assert tier == HardwareTier.STANDARD


def test_classify_gpu_workstation(gpu_workstation_profile):
    """64GB workstation with NVIDIA RTX 4090 (24GB VRAM) must be classified as HIGH."""
    tier = TierClassifier.classify(
        cpu=gpu_workstation_profile.cpu,
        memory=gpu_workstation_profile.memory,
        gpu=gpu_workstation_profile.gpu,
        accelerators=gpu_workstation_profile.accelerators,
    )
    assert tier == HardwareTier.HIGH


def test_classify_apple_silicon_high(apple_silicon_high_profile):
    """Apple Silicon workstation with 36GB unified memory must be classified as HIGH."""
    tier = TierClassifier.classify(
        cpu=apple_silicon_high_profile.cpu,
        memory=apple_silicon_high_profile.memory,
        gpu=apple_silicon_high_profile.gpu,
        accelerators=apple_silicon_high_profile.accelerators,
    )
    assert tier == HardwareTier.HIGH


def test_classify_apple_silicon_base():
    """Apple Silicon base (8GB total, 2.5GB free) must be classified as BASELINE."""
    cpu = CPUInfo(
        architecture="arm64",
        vendor="Apple",
        model="Apple M1",
        logical_cores=8,
        physical_cores=8,
        features=["neon"],
    )
    memory = MemoryInfo(total_bytes=8 * 1024**3, available_bytes=int(2.5 * 1024**3))
    gpu = GPUInfo(
        available=True,
        type="apple_silicon",
        model="Apple M1 GPU",
        vram_bytes=8 * 1024**3,
        unified_memory=True,
    )
    tier = TierClassifier.classify(
        cpu=cpu,
        memory=memory,
        gpu=gpu,
        accelerators=["apple_silicon"],
    )
    assert tier == HardwareTier.BASELINE


def test_conservative_memory_downgrade():
    """If free RAM is dangerously low (< 2.5GB), downgrade to BASELINE."""
    cpu = CPUInfo(
        architecture="x86_64",
        vendor="Intel",
        model="i7-12700H",
        logical_cores=16,
        physical_cores=14,
        features=["avx2"],
    )
    # 32GB total, but only 1.2GB available due to heavy system load
    memory = MemoryInfo(total_bytes=32 * 1024**3, available_bytes=int(1.2 * 1024**3))
    gpu = GPUInfo(
        available=True,
        type="nvidia_cuda",
        model="RTX 3070",
        vram_bytes=8 * 1024**3,
        unified_memory=False,
    )
    tier = TierClassifier.classify(
        cpu=cpu,
        memory=memory,
        gpu=gpu,
        accelerators=["nvidia_cuda"],
    )
    # Must be downgraded to BASELINE to prevent OOM
    assert tier == HardwareTier.BASELINE


def test_power_mode_throttling(gpu_workstation_profile):
    """Low power mode degrades HIGH to STANDARD to respect battery/thermal limits."""
    tier = TierClassifier.classify(
        cpu=gpu_workstation_profile.cpu,
        memory=gpu_workstation_profile.memory,
        gpu=gpu_workstation_profile.gpu,
        accelerators=gpu_workstation_profile.accelerators,
        power_mode="low_power",
    )
    assert tier == HardwareTier.STANDARD
