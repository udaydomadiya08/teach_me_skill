"""Event system interface for asynchronous, decoupled event distribution."""

from abc import ABC, abstractmethod
from typing import Any, Callable


class IEvent(ABC):
    """Base event contract."""

    @property
    @abstractmethod
    def event_type(self) -> str:
        """Name or category of the event."""
        pass

    @property
    @abstractmethod
    def timestamp(self) -> float:
        """UTC epoch timestamp of the event."""
        pass


class IEventSystem(ABC):
    """Pub/Sub event broker interface for timeline and recorder events."""

    @abstractmethod
    def subscribe(self, event_type: str, handler: Callable[[Any], None]) -> str:
        """Subscribe a handler to an event type. Returns a subscription ID."""
        pass

    @abstractmethod
    def unsubscribe(self, subscription_id: str) -> None:
        """Remove a subscription."""
        pass

    @abstractmethod
    def publish(self, event: IEvent) -> None:
        """Publish an event to all active subscribers."""
        pass
