"""Privacy and policy verification interfaces."""

from abc import ABC, abstractmethod


class IPrivacyPolicy(ABC):
    """Abstract interface defining the privacy contract and operational limits."""

    @property
    @abstractmethod
    def local_only(self) -> bool:
        """Indicates whether all operations are strictly confined locally."""
        pass

    @property
    @abstractmethod
    def allow_network(self) -> bool:
        """Indicates whether external network access is permitted."""
        pass

    @property
    @abstractmethod
    def telemetry_enabled(self) -> bool:
        """Indicates whether telemetry or usage analytics are allowed."""
        pass

    @property
    @abstractmethod
    def cloud_inference_enabled(self) -> bool:
        """Indicates whether remote/cloud AI inference is permitted."""
        pass


class IPrivacyGuard(ABC):
    """Runtime guard interface preventing operations that violate policy."""

    @abstractmethod
    def assert_network_allowed(self, target: str) -> None:
        """Raise PrivacyViolationError if network access is denied."""
        pass

    @abstractmethod
    def assert_telemetry_allowed(self) -> None:
        """Raise PrivacyViolationError if telemetry is denied."""
        pass

    @abstractmethod
    def assert_cloud_inference_allowed(self) -> None:
        """Raise PrivacyViolationError if cloud inference is denied."""
        pass

    @abstractmethod
    def assert_screen_capture_allowed(self) -> None:
        """Raise PrivacyViolationError if screen capture is not permitted."""
        pass

    @abstractmethod
    def assert_microphone_allowed(self) -> None:
        """Raise PrivacyViolationError if audio capture is not permitted."""
        pass
