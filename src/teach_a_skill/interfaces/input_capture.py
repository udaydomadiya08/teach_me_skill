"""Input capture interface (Phase 2 contract)."""

from abc import ABC, abstractmethod
from typing import Callable


class IInputCapture(ABC):
    """Deterministic OS-level mouse and keyboard event capture interface."""

    @abstractmethod
    def start_hook(self, event_callback: Callable[[dict], None]) -> None:
        """Start listening for mouse/keyboard inputs via OS hooks."""
        pass

    @abstractmethod
    def stop_hook(self) -> None:
        """Unhook and release event listeners."""
        pass
