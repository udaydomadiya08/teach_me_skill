"""Base platform adapter implementation with capability matrix and compatibility manifest."""

from __future__ import annotations

import platform
from abc import abstractmethod
from typing import Optional

from teach_a_skill.interfaces.platform import IPlatformAdapter
from teach_a_skill.platform.capabilities import (
    CapabilityState,
    PlatformCapabilities,
    PlatformCapability,
    PlatformCompatibilityManifest,
)


class BasePlatformAdapter(IPlatformAdapter):
    """Abstract base class providing common cross-platform utility methods and capability reporting."""

    @property
    def system_type(self) -> str:
        return platform.system().lower()

    def get_os_version(self) -> str:
        return f"{platform.system()} {platform.release()} ({platform.version()})"

    def is_supported(self) -> bool:
        return self.system_type in ("darwin", "linux", "windows")

    @abstractmethod
    def get_desktop_environment(self) -> Optional[str]:
        pass

    @abstractmethod
    def get_default_data_dir(self) -> str:
        pass

    @abstractmethod
    def get_capabilities(self) -> PlatformCapabilities:
        """Probe and return the host platform capability matrix."""
        pass

    @abstractmethod
    def get_compatibility_manifest(self) -> PlatformCompatibilityManifest:
        """Return the declared platform compatibility manifest."""
        pass
