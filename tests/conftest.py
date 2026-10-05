"""Shared pytest fixtures."""

import tempfile
from pathlib import Path

import pytest

from teach_a_skill.config.defaults import get_default_config
from teach_a_skill.config.manager import ConfigManager
from teach_a_skill.hardware.profile import (
    CPUInfo,
    GPUInfo,
    HardwareProfile,
    MemoryInfo,
    StorageInfo,
)
from teach_a_skill.storage.manager import StorageManager


@pytest.fixture
def temp_dir():
    """Provide a temporary directory that is cleaned up after each test."""
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def storage_mgr(temp_dir):
    """Provide an initialized StorageManager pointing to a temporary directory."""
    sm = StorageManager(temp_dir / "app_data")
    sm.initialize_directories()
    return sm


@pytest.fixture
def config_mgr(temp_dir):
    """Provide a ConfigManager configured to a temporary location."""
    cfg_path = temp_dir / "config.json"
    mgr = ConfigManager(cfg_path)
    cfg = get_default_config()
    cfg.storage.data_directory = str(temp_dir / "app_data")
    mgr.set_config(cfg)
    return mgr


# --- Mock Profiles for Tier Testing ---


@pytest.fixture
def weak_cpu_profile():
    """Weak CPU-only machine (2 cores, 4GB RAM, no GPU)."""
    return HardwareProfile(
        platform="linux",
        os_version="Linux 5.15",
        architecture="x86_64",
        cpu=CPUInfo(
            architecture="x86_64",
            vendor="Intel",
            model="Celeron N4020",
            logical_cores=2,
            physical_cores=2,
            features=[],
        ),
        memory=MemoryInfo(
            total_bytes=4 * 1024**3,
            available_bytes=1024**3,
        ),
        gpu=GPUInfo(
            available=False,
            type="none",
            model="Integrated",
            vram_bytes=None,
            unified_memory=False,
        ),
        accelerators=[],
        storage=StorageInfo(
            target_path="/tmp",
            total_bytes=64 * 1024**3,
            free_bytes=20 * 1024**3,
        ),
        capability_class="BASELINE",
    )


@pytest.fixture
def laptop_8gb_profile():
    """Standard budget 8GB laptop (4 cores, 8GB RAM, integrated GPU)."""
    return HardwareProfile(
        platform="windows",
        os_version="Windows 11",
        architecture="x86_64",
        cpu=CPUInfo(
            architecture="x86_64",
            vendor="Intel",
            model="Core i5-1135G7",
            logical_cores=4,
            physical_cores=4,
            features=["avx2"],
        ),
        memory=MemoryInfo(
            total_bytes=8 * 1024**3,
            available_bytes=3 * 1024**3,
        ),
        gpu=GPUInfo(
            available=False,
            type="none",
            model="Intel Iris Xe",
            vram_bytes=None,
            unified_memory=False,
        ),
        accelerators=[],
        storage=StorageInfo(
            target_path="C:\\",
            total_bytes=256 * 1024**3,
            free_bytes=80 * 1024**3,
        ),
        capability_class="BASELINE",
    )


@pytest.fixture
def laptop_16gb_profile():
    """Modern 16GB laptop (8 cores, 16GB RAM, 8GB available, modest accelerator)."""
    return HardwareProfile(
        platform="linux",
        os_version="Ubuntu 22.04",
        architecture="x86_64",
        cpu=CPUInfo(
            architecture="x86_64",
            vendor="AMD",
            model="Ryzen 7 5800U",
            logical_cores=8,
            physical_cores=8,
            features=["avx2", "fma"],
        ),
        memory=MemoryInfo(
            total_bytes=16 * 1024**3,
            available_bytes=8 * 1024**3,
        ),
        gpu=GPUInfo(
            available=False,
            type="none",
            model="Radeon Vega 8",
            vram_bytes=None,
            unified_memory=False,
        ),
        accelerators=[],
        storage=StorageInfo(
            target_path="/home/user",
            total_bytes=512 * 1024**3,
            free_bytes=200 * 1024**3,
        ),
        capability_class="STANDARD",
    )


@pytest.fixture
def gpu_workstation_profile():
    """High-end workstation (16 cores, 64GB RAM, NVIDIA RTX 4090 24GB VRAM)."""
    return HardwareProfile(
        platform="linux",
        os_version="Ubuntu 24.04",
        architecture="x86_64",
        cpu=CPUInfo(
            architecture="x86_64",
            vendor="Intel",
            model="Core i9-14900K",
            logical_cores=24,
            physical_cores=16,
            features=["avx2", "fma"],
        ),
        memory=MemoryInfo(
            total_bytes=64 * 1024**3,
            available_bytes=48 * 1024**3,
        ),
        gpu=GPUInfo(
            available=True,
            type="nvidia_cuda",
            model="NVIDIA GeForce RTX 4090",
            vram_bytes=24 * 1024**3,
            unified_memory=False,
        ),
        accelerators=["nvidia_cuda"],
        storage=StorageInfo(
            target_path="/data",
            total_bytes=2048 * 1024**3,
            free_bytes=1200 * 1024**3,
        ),
        capability_class="HIGH",
    )


@pytest.fixture
def apple_silicon_high_profile():
    """Apple Silicon workstation (12 cores, 36GB unified memory, 20GB available)."""
    return HardwareProfile(
        platform="macos",
        os_version="macOS 15.0",
        architecture="arm64",
        cpu=CPUInfo(
            architecture="arm64",
            vendor="Apple",
            model="Apple M3 Max",
            logical_cores=14,
            physical_cores=14,
            features=["neon"],
        ),
        memory=MemoryInfo(
            total_bytes=36 * 1024**3,
            available_bytes=20 * 1024**3,
        ),
        gpu=GPUInfo(
            available=True,
            type="apple_silicon",
            model="Apple Silicon GPU (Metal Unified Memory)",
            vram_bytes=36 * 1024**3,
            unified_memory=True,
        ),
        accelerators=["apple_silicon"],
        storage=StorageInfo(
            target_path="/Users/test",
            total_bytes=1000 * 1024**3,
            free_bytes=400 * 1024**3,
        ),
        capability_class="HIGH",
    )
