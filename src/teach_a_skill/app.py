"""Application orchestrator for Teach A Skill."""

from pathlib import Path
from typing import Any, Optional

from teach_a_skill.config.manager import ConfigManager
from teach_a_skill.core.logging import get_logger, setup_logger
from teach_a_skill.hardware.budget import BudgetCalculator, ResourceBudget
from teach_a_skill.hardware.detector import HardwareDetector
from teach_a_skill.hardware.profile import HardwareProfile
from teach_a_skill.interfaces.application import IApplication
from teach_a_skill.models.registry import ModelRegistry
from teach_a_skill.privacy.guard import PrivacyGuard
from teach_a_skill.storage.manager import StorageManager

logger = get_logger("teach_a_skill.app")


class TeachSkillApp(IApplication):
    """Main application lifecycle controller for Phase 1.

    Initializes platform adapters, hardware detector, resource budgeting,
    local storage sandbox, privacy guard, and model catalog without requiring
    any AI models or GPU hardware to run.
    """

    def __init__(self, config_path: Optional[Path] = None, quiet: bool = False) -> None:
        self.config_manager = ConfigManager(config_path)
        self.quiet = quiet
        self._initialized = False

        self.config = self.config_manager.get_config()
        self.privacy_policy = self.config_manager.get_privacy_policy()
        self.privacy_guard = PrivacyGuard(self.privacy_policy)

        # Storage
        data_dir = Path(self.config.storage.data_directory)
        self.storage_manager = StorageManager(data_dir)

        # Hardware & Budget
        self.hardware_detector = HardwareDetector(str(data_dir))
        self._hardware_profile: Optional[HardwareProfile] = None
        self._resource_budget: Optional[ResourceBudget] = None

        # Model Registry
        self.model_registry = ModelRegistry()

        # Demonstration Recorder
        self._recorder = None

        # Teaching Orchestrator (Phase 3)
        self._teaching_orchestrator = None

    def initialize(self) -> None:
        """Initialize core application services, configuration, and storage."""
        if self._initialized:
            return

        # Setup logging
        log_level = "WARNING" if self.quiet else self.config.logging.level
        setup_logger(
            level=log_level,
            json_format=self.config.logging.json_format,
        )

        if not self.quiet:
            logger.info("Initializing Teach A Skill (Phase 1 Foundation)...")

        # 1. Initialize local storage sandboxes
        self.storage_manager.initialize_directories()

        # 2. Run deterministic hardware detection
        self._hardware_profile = self.hardware_detector.get_profile()

        # 3. Calculate safe resource budget
        self._resource_budget = BudgetCalculator.calculate(
            self._hardware_profile,
            power_mode=self.config.performance.power_mode,
            memory_limit_override_mb=self.config.performance.max_memory_mb,
        )

        logger.info(
            "Hardware initialized",
            extra={
                "tier": self._hardware_profile.capability_class,
                "ram_gb": self._hardware_profile.memory.total_gb,
                "budget_max_mb": self._resource_budget.max_memory_mb,
                "model_class": self._resource_budget.preferred_model_class,
            },
        )

        self._initialized = True

    def shutdown(self) -> None:
        """Gracefully release resources, flush storage buffers, and terminate."""
        if not self._initialized:
            return
        logger.info("Shutting down Teach A Skill...")
        self._initialized = False

    def get_hardware_profile(self) -> HardwareProfile:
        """Get or compute hardware profile."""
        if self._hardware_profile is None:
            self._hardware_profile = self.hardware_detector.get_profile()
        return self._hardware_profile

    def get_resource_budget(self) -> ResourceBudget:
        """Get or compute resource budget."""
        if self._resource_budget is None:
            profile = self.get_hardware_profile()
            self._resource_budget = BudgetCalculator.calculate(
                profile,
                power_mode=self.config.performance.power_mode,
                memory_limit_override_mb=self.config.performance.max_memory_mb,
            )
        return self._resource_budget

    def get_recorder(self, capture_profile: Optional[Any] = None) -> Any:
        """Get or initialize UniversalRecorder configured with adaptive hardware settings."""
        if self._recorder is None:
            from teach_a_skill.recorder.recorder import UniversalRecorder
            from teach_a_skill.recorder.screen import CaptureProfile

            profile = self.get_hardware_profile()
            budget = self.get_resource_budget()

            if capture_profile is None:
                if str(budget.tier) == "BASELINE":
                    selected_profile = CaptureProfile.MINIMAL
                elif str(budget.tier) == "STANDARD":
                    selected_profile = CaptureProfile.BALANCED
                else:
                    selected_profile = CaptureProfile.HIGH
            else:
                selected_profile = CaptureProfile(capture_profile)

            self._recorder = UniversalRecorder(
                storage_manager=self.storage_manager,
                capture_profile=selected_profile,
                platform_name=profile.platform,
                architecture=profile.architecture,
                hardware_profile=profile.to_dict(),
            )
        return self._recorder

    def get_teaching_orchestrator(self) -> Any:
        """Get or initialize TeachingOrchestrator for voice and text teaching."""
        if self._teaching_orchestrator is None:
            from teach_a_skill.teaching.orchestrator import TeachingOrchestrator

            self._teaching_orchestrator = TeachingOrchestrator(
                storage_manager=self.storage_manager,
                privacy_guard=self.privacy_guard,
                model_registry=self.model_registry,
                resource_budget=self.get_resource_budget(),
            )
        return self._teaching_orchestrator

    def get_status(self) -> dict[str, Any]:
        """Return diagnostic status information for the running application."""
        profile = self.get_hardware_profile()
        budget = self.get_resource_budget()
        recorder = self.get_recorder()
        teaching = self.get_teaching_orchestrator()

        return {
            "initialized": self._initialized,
            "version": "0.2.0",
            "phase_version": "0.3.0",
            "phase": 3,
            "privacy": self.privacy_policy.to_dict(),
            "hardware": {
                "platform": profile.platform,
                "architecture": profile.architecture,
                "tier": profile.capability_class,
                "ram_total_gb": profile.memory.total_gb,
                "ram_available_gb": profile.memory.available_gb,
                "cpu_cores": profile.cpu.logical_cores,
                "cpu_model": profile.cpu.model,
                "gpu_available": profile.gpu.available,
                "gpu_type": profile.gpu.type,
            },
            "budget": budget.to_dict(),
            "recorder": {
                "active": recorder.is_recording,
                "paused": recorder.is_paused,
                "capture_profile": str(recorder.capture_profile),
            },
            "teaching": {
                "active": teaching.is_teaching,
                "paused": teaching.is_paused,
                "audio_enabled": teaching.enable_audio,
                "transcription_enabled": teaching.enable_transcription,
            },
            "storage": {
                "base_dir": str(self.storage_manager.base_dir),
                "storage_free_gb": profile.storage.free_gb,
            },
            "models": {
                "registered_descriptors": len(self.model_registry.list_models()),
                "compatible_models": len(self.model_registry.find_compatible_models(budget)),
            },
        }
