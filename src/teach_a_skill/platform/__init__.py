"""Platform detection, adapter factory, capability matrix, and platform manager."""

from __future__ import annotations

from teach_a_skill.interfaces.platform import IPlatformAdapter
from teach_a_skill.platform.base import BasePlatformAdapter
from teach_a_skill.platform.capabilities import (
    CapabilityReport,
    CapabilityState,
    PlatformCapabilities,
    PlatformCapability,
    PlatformCompatibilityManifest,
)
from teach_a_skill.platform.linux import LinuxAdapter, LinuxPlatformAdapter
from teach_a_skill.platform.macos import MacOSAdapter, MacOSPlatformAdapter
from teach_a_skill.platform.manager import PlatformManager
from teach_a_skill.platform.windows import WindowsAdapter, WindowsPlatformAdapter


def get_platform_adapter() -> BasePlatformAdapter:
    """Return the platform-specific adapter for the current host OS."""
    return PlatformManager.get_adapter()


__all__ = [
    "get_platform_adapter",
    "PlatformManager",
    "BasePlatformAdapter",
    "MacOSAdapter",
    "MacOSPlatformAdapter",
    "LinuxAdapter",
    "LinuxPlatformAdapter",
    "WindowsAdapter",
    "WindowsPlatformAdapter",
    "IPlatformAdapter",
    "CapabilityState",
    "PlatformCapability",
    "CapabilityReport",
    "PlatformCapabilities",
    "PlatformCompatibilityManifest",
]
