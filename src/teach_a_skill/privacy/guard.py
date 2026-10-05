"""Privacy guard runtime enforcement."""

from teach_a_skill.core.errors import PrivacyViolationError
from teach_a_skill.core.logging import get_logger
from teach_a_skill.interfaces.privacy import IPrivacyGuard
from teach_a_skill.privacy.policy import PrivacyPolicy

logger = get_logger("teach_a_skill.privacy")


class PrivacyGuard(IPrivacyGuard):
    """Runtime guard enforcing privacy invariants across all application layers."""

    def __init__(self, policy: PrivacyPolicy) -> None:
        self._policy = policy

    @property
    def policy(self) -> PrivacyPolicy:
        return self._policy

    def assert_network_allowed(self, target: str) -> None:
        """Enforces that network access is never made when allow_network is False."""
        if not self._policy.allow_network:
            logger.warning("Attempted blocked network access", extra={"target": target})
            raise PrivacyViolationError(
                f"Network access is prohibited by active Privacy Policy (target='{target}'). "
                "Teach A Skill operates strictly local-only."
            )

    def assert_telemetry_allowed(self) -> None:
        """Enforces that telemetry or analytics cannot be dispatched."""
        if not self._policy.telemetry_enabled:
            logger.warning("Attempted blocked telemetry dispatch")
            raise PrivacyViolationError(
                "Telemetry collection is disabled by Privacy Policy. No usage data may leave the machine."
            )

    def assert_cloud_inference_allowed(self) -> None:
        """Enforces that model inference is strictly local."""
        if not self._policy.cloud_inference_enabled:
            logger.warning("Attempted blocked cloud inference call")
            raise PrivacyViolationError(
                "Cloud inference is disabled by Privacy Policy. All models must execute on local hardware."
            )

    def assert_screen_capture_allowed(self) -> None:
        """Enforces that screen capture is only initiated when explicitly permitted."""
        if not self._policy.screen_capture_allowed:
            raise PrivacyViolationError(
                "Screen capture is disabled by Privacy Policy. Active recording session required."
            )

    def assert_microphone_allowed(self) -> None:
        """Enforces that audio capture is only initiated when explicitly permitted."""
        if not self._policy.microphone_allowed:
            raise PrivacyViolationError(
                "Microphone access is disabled by Privacy Policy. Active voice session required."
            )

    def assert_can_persist(self, data_type: str) -> None:
        """Enforces that persistence respects local storage privacy."""
        if not self._policy.persist_user_content:
            raise PrivacyViolationError(
                f"Data persistence is disabled by Privacy Policy for type: {data_type}"
            )
