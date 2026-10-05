"""Tests for hardware detection."""

from unittest.mock import patch

from teach_a_skill.hardware.detector import HardwareDetector
from teach_a_skill.hardware.profile import HardwareProfile


def test_real_hardware_detection():
    """Verify hardware detector on active host produces valid profile."""
    detector = HardwareDetector()
    profile = detector.get_profile()

    assert isinstance(profile, HardwareProfile)
    assert profile.platform in ("macos", "linux", "windows")
    assert profile.architecture != ""
    assert profile.cpu.logical_cores >= 1
    assert profile.memory.total_bytes > 0
    assert profile.memory.available_bytes > 0
    assert profile.storage.total_bytes > 0
    assert profile.capability_class in ("BASELINE", "STANDARD", "HIGH")


def test_hardware_detector_graceful_cpu_fallback():
    """Verify hardware detector survives unexpected subprocess errors."""
    detector = HardwareDetector()

    with patch("subprocess.check_output", side_effect=OSError("command not found")):
        cpu = detector.detect_cpu()
        assert cpu.logical_cores >= 1
        assert isinstance(cpu.model, str)


def test_hardware_detector_graceful_memory_fallback():
    """Verify memory detection falls back to safe non-zero values if system calls fail."""
    detector = HardwareDetector()

    with patch("subprocess.check_output", side_effect=OSError("sysctl failed")):
        with patch("os.sysconf", side_effect=ValueError("sysconf failed")):
            mem = detector.detect_memory()
            assert mem.total_bytes > 0
            assert mem.available_bytes > 0
            assert mem.total_gb >= 1.0


def test_hardware_detector_graceful_gpu_fallback():
    """Verify GPU detection falls back to CPU-only if no GPU is found."""
    detector = HardwareDetector()

    with patch("shutil.which", return_value=None):
        with patch("platform.system", return_value="Linux"):
            gpu = detector.detect_gpu()
            assert gpu.available is False
            assert gpu.type == "none"
