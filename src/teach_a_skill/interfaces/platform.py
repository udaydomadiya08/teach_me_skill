"""Cross-platform abstraction boundaries."""

from abc import ABC, abstractmethod
from typing import Optional


class IPlatformAdapter(ABC):
    """Platform-specific adapter interface to abstract OS differences."""

    @property
    @abstractmethod
    def os_name(self) -> str:
        """Normalized OS name: 'macos', 'linux', or 'windows'."""
        pass

    @abstractmethod
    def get_os_version(self) -> str:
        """Detailed OS version string."""
        pass

    @abstractmethod
    def get_desktop_environment(self) -> Optional[str]:
        """Desktop environment (e.g., Aqua, GNOME, KDE, Windows Shell)."""
        pass

    @abstractmethod
    def get_default_data_dir(self) -> str:
        """Returns standard OS-compliant local application data path."""
        pass

    @abstractmethod
    def is_supported(self) -> bool:
        """Checks if current platform meets minimum OS requirements."""
        pass
