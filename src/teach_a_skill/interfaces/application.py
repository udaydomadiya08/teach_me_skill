"""Application lifecycle and orchestration interface."""

from abc import ABC, abstractmethod
from typing import Any


class IApplication(ABC):
    """Core application lifecycle interface."""

    @abstractmethod
    def initialize(self) -> None:
        """Initialize core application services, configuration, and storage."""
        pass

    @abstractmethod
    def shutdown(self) -> None:
        """Gracefully release resources, flush storage buffers, and terminate."""
        pass

    @abstractmethod
    def get_status(self) -> dict[str, Any]:
        """Return diagnostic status information for the running application."""
        pass
