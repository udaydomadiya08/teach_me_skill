"""Window manager and application context interface (Phase 2 contract)."""

from abc import ABC, abstractmethod
from typing import Any, Optional


class IWindowManager(ABC):
    """Deterministic OS-level window hierarchy and focused application detector."""

    @abstractmethod
    def get_active_window(self) -> Optional[dict[str, Any]]:
        """Retrieve title, bounds, process name, and PID of the focused window."""
        pass

    @abstractmethod
    def list_windows(self) -> list[dict[str, Any]]:
        """Enumerate visible application windows."""
        pass
