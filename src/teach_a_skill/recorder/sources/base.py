"""Base event source contract."""

from abc import ABC, abstractmethod
from typing import Callable

from teach_a_skill.recorder.events import Event


class BaseEventSource(ABC):
    """Abstract provider of demonstration interaction events."""

    @abstractmethod
    def start(self, callback: Callable[[Event], None]) -> None:
        """Start capturing or generating events, invoking callback for each event."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Halt event emission and release hooks/timers."""
        pass

    @property
    @abstractmethod
    def is_active(self) -> bool:
        """Return True if event source is currently active."""
        pass
