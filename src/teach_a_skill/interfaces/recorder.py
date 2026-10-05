"""Universal recorder interface (Phase 2 contract)."""

from abc import ABC, abstractmethod
from typing import Any, Optional


class IRecorder(ABC):
    """Contract for demonstration recording system (Scheduled for Phase 2)."""

    @abstractmethod
    def start_recording(self, session_id: str, metadata: Optional[dict[str, Any]] = None) -> None:
        """Begin capturing screen, input events, and window contexts."""
        pass

    @abstractmethod
    def pause_recording(self) -> None:
        """Pause active recording."""
        pass

    @abstractmethod
    def resume_recording(self) -> None:
        """Resume paused recording."""
        pass

    @abstractmethod
    def stop_recording(self) -> str:
        """Stop recording and return the storage path to the raw session."""
        pass

    @property
    @abstractmethod
    def is_recording(self) -> bool:
        """Returns True if recording is currently active."""
        pass
