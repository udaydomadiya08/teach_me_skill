"""Local hardware capability detector.

Gathers deterministic hardware metrics without external network or heavy dependencies.
"""

import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from teach_a_skill.hardware.profile import (
    CPUInfo,
    GPUInfo,
    HardwareProfile,
    MemoryInfo,
    StorageInfo,
)
from teach_a_skill.hardware.tiers import TierClassifier
from teach_a_skill.interfaces.hardware import IHardwareDetector
from teach_a_skill.platform import get_platform_adapter


class HardwareDetector(IHardwareDetector):
    """Detects CPU, Memory, GPU/Accelerators, OS, and Storage."""

    def __init__(self, target_data_dir: Optional[str] = None) -> None:
        self.platform_adapter = get_platform_adapter()
        self.target_data_dir = target_data_dir or self.platform_adapter.get_default_data_dir()

    def detect_cpu(self) -> CPUInfo:
        """Detect CPU architecture, vendor, model, and logical/physical cores."""
        arch = platform.machine().lower()
        logical_cores = os.cpu_count() or 1
        physical_cores = logical_cores
        vendor = "Unknown"
        model = platform.processor() or "Unknown Processor"
        features: list[str] = []

        sys_name = platform.system().lower()

        perf_cores: Optional[int] = None
        eff_cores: Optional[int] = None

        if sys_name == "darwin":
            try:
                out = subprocess.check_output(
                    ["sysctl", "-n", "machdep.cpu.brand_string"],
                    text=True,
                    stderr=subprocess.DEVNULL,
                ).strip()
                if out:
                    model = out
            except Exception:
                pass

            try:
                phys_out = subprocess.check_output(
                    ["sysctl", "-n", "hw.physicalcpu"],
                    text=True,
                    stderr=subprocess.DEVNULL,
                ).strip()
                if phys_out.isdigit():
                    physical_cores = int(phys_out)
            except Exception:
                pass

            try:
                p_out = subprocess.check_output(
                    ["sysctl", "-n", "hw.perflevel0.physicalcpu"],
                    text=True,
                    stderr=subprocess.DEVNULL,
                ).strip()
                if p_out.isdigit():
                    perf_cores = int(p_out)
            except Exception:
                pass

            try:
                e_out = subprocess.check_output(
                    ["sysctl", "-n", "hw.perflevel1.physicalcpu"],
                    text=True,
                    stderr=subprocess.DEVNULL,
                ).strip()
                if e_out.isdigit():
                    eff_cores = int(e_out)
            except Exception:
                pass

            if "apple" in model.lower() or arch == "arm64":
                vendor = "Apple"
                features.append("neon")
            elif "intel" in model.lower():
                vendor = "Intel"

        elif sys_name == "linux":
            try:
                if os.path.exists("/proc/cpuinfo"):
                    with open("/proc/cpuinfo", "r", encoding="utf-8") as f:
                        cpuinfo = f.read()
                    for line in cpuinfo.splitlines():
                        if ":" in line:
                            k, v = [x.strip() for x in line.split(":", 1)]
                            if k == "model name" and model == "Unknown Processor":
                                model = v
                            elif k == "vendor_id" and vendor == "Unknown":
                                vendor = v
                            elif k == "flags":
                                for flag in ("avx", "avx2", "fma", "sse4_2"):
                                    if flag in v and flag not in features:
                                        features.append(flag)
            except Exception:
                pass

        elif sys_name == "windows":
            vendor = os.environ.get("PROCESSOR_IDENTIFIER", "Unknown")

        return CPUInfo(
            architecture=arch,
            vendor=vendor,
            model=model,
            logical_cores=logical_cores,
            physical_cores=physical_cores,
            features=features,
            performance_cores=perf_cores,
            efficiency_cores=eff_cores,
        )

    def detect_memory(self) -> MemoryInfo:
        """Detect total and currently available system RAM in bytes."""
        total_bytes = 0
        available_bytes = 0
        sys_name = platform.system().lower()

        if sys_name == "darwin":
            try:
                memsize_out = subprocess.check_output(
                    ["sysctl", "-n", "hw.memsize"],
                    text=True,
                    stderr=subprocess.DEVNULL,
                ).strip()
                if memsize_out.isdigit():
                    total_bytes = int(memsize_out)
            except Exception:
                pass

            # Estimate available memory from vm_stat
            try:
                vm_out = subprocess.check_output(["vm_stat"], text=True, stderr=subprocess.DEVNULL)
                page_size = 4096
                free_pages = 0
                inactive_pages = 0
                for line in vm_out.splitlines():
                    if "page size of" in line:
                        parts = line.split()
                        for p in parts:
                            if p.isdigit():
                                page_size = int(p)
                                break
                    elif "Pages free:" in line:
                        free_pages = int(line.split(":")[1].strip().rstrip("."))
                    elif "Pages inactive:" in line:
                        inactive_pages = int(line.split(":")[1].strip().rstrip("."))
                available_bytes = (free_pages + inactive_pages) * page_size
            except Exception:
                # Fallback: assume ~40% available if vm_stat fails
                available_bytes = int(total_bytes * 0.40)

        elif sys_name == "linux":
            try:
                if os.path.exists("/proc/meminfo"):
                    with open("/proc/meminfo", "r", encoding="utf-8") as f:
                        for line in f:
                            if line.startswith("MemTotal:"):
                                total_bytes = int(line.split()[1]) * 1024
                            elif line.startswith("MemAvailable:"):
                                available_bytes = int(line.split()[1]) * 1024
            except Exception:
                pass

        elif sys_name == "windows":
            try:
                import ctypes

                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                    ]

                stat = MEMORYSTATUSEX()
                stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                    total_bytes = stat.ullTotalPhys
                    available_bytes = stat.ullAvailPhys
            except Exception:
                pass

        # Universal fallback if OS specific calls failed
        if total_bytes == 0:
            try:
                total_bytes = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
                available_bytes = int(total_bytes * 0.40)
            except Exception:
                # Safe conservative default: 4GB total, 1GB available
                total_bytes = 4 * 1024 * 1024 * 1024
                available_bytes = 1024 * 1024 * 1024

        return MemoryInfo(total_bytes=total_bytes, available_bytes=available_bytes)

    def detect_gpu(self) -> GPUInfo:
        """Detect available GPU, accelerator devices, and Metal/CUDA runtimes."""
        sys_name = platform.system().lower()
        arch = platform.machine().lower()

        # Check 1: Apple Silicon with Metal (macOS arm64)
        if sys_name == "darwin" and arch == "arm64":
            mem = self.detect_memory()
            return GPUInfo(
                available=True,
                type="apple_silicon",
                model="Apple Silicon GPU (Metal Unified Memory)",
                vram_bytes=mem.total_bytes,
                unified_memory=True,
            )

        # Check 2: NVIDIA CUDA via nvidia-smi
        nvidia_smi = shutil.which("nvidia-smi")
        if nvidia_smi:
            try:
                out = subprocess.check_output(
                    [
                        nvidia_smi,
                        "--query-gpu=name,memory.total",
                        "--format=csv,noheader,nounits",
                    ],
                    text=True,
                    stderr=subprocess.DEVNULL,
                ).strip()
                if out:
                    first_line = out.splitlines()[0]
                    parts = first_line.split(",")
                    name = parts[0].strip()
                    vram_mb = int(parts[1].strip()) if len(parts) > 1 else 0
                    return GPUInfo(
                        available=True,
                        type="nvidia_cuda",
                        model=name,
                        vram_bytes=vram_mb * 1024 * 1024,
                        unified_memory=False,
                    )
            except Exception:
                pass

        # Check 3: AMD ROCm
        rocm_smi = shutil.which("rocm-smi")
        if rocm_smi:
            try:
                return GPUInfo(
                    available=True,
                    type="amd_rocm",
                    model="AMD Radeon / ROCm Accelerator",
                    vram_bytes=None,
                    unified_memory=False,
                )
            except Exception:
                pass

        # Check 4: Integrated / Default CPU only fallback
        return GPUInfo(
            available=False,
            type="none",
            model="None (CPU Only)",
            vram_bytes=None,
            unified_memory=False,
        )

    def detect_storage(self, target_path: Optional[str] = None) -> StorageInfo:
        """Detect total and free storage space on target volume in bytes."""
        path_to_check = target_path or self.target_data_dir
        # Ensure path or parent exists for disk_usage query
        p = Path(path_to_check).expanduser()
        while not p.exists() and p.parent != p:
            p = p.parent

        try:
            usage = shutil.disk_usage(str(p))
            total = usage.total
            free = usage.free
        except Exception:
            total = 50 * 1024 * 1024 * 1024
            free = 10 * 1024 * 1024 * 1024

        return StorageInfo(
            target_path=str(path_to_check),
            total_bytes=total,
            free_bytes=free,
        )

    def get_profile(self) -> HardwareProfile:
        """Return the normalized hardware capability profile."""
        import sys

        cpu = self.detect_cpu()
        mem = self.detect_memory()
        gpu = self.detect_gpu()
        storage = self.detect_storage()

        accelerators: list[str] = []
        if gpu.available:
            accelerators.append(gpu.type)

        tier = TierClassifier.classify(cpu=cpu, memory=mem, gpu=gpu, accelerators=accelerators)

        metal_available = False
        sys_name = platform.system().lower()
        if sys_name == "darwin" and (cpu.architecture == "arm64" or gpu.type == "apple_silicon"):
            metal_available = True

        cuda_available = gpu.type == "nvidia_cuda"
        rocm_available = gpu.type == "amd_rocm"
        neural_engine_available = sys_name == "darwin" and cpu.architecture == "arm64"

        frameworks: dict[str, str] = {}
        for fw in ("torch", "onnxruntime", "numpy", "PIL"):
            try:
                mod = __import__(fw)
                frameworks[fw] = str(getattr(mod, "__version__", "present"))
            except Exception:
                pass

        return HardwareProfile(
            platform=self.platform_adapter.os_name,
            os_version=self.platform_adapter.get_os_version(),
            architecture=cpu.architecture,
            cpu=cpu,
            memory=mem,
            gpu=gpu,
            accelerators=accelerators,
            storage=storage,
            capability_class=tier.value,
            metal_available=metal_available,
            cuda_available=cuda_available,
            rocm_available=rocm_available,
            neural_engine_available=neural_engine_available,
            python_runtime=sys.version.split()[0],
            framework_versions=frameworks,
        )

