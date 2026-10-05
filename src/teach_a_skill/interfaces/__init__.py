"""Core architectural interfaces for Teach A Skill."""

from teach_a_skill.interfaces.application import IApplication
from teach_a_skill.interfaces.event_system import IEvent, IEventSystem
from teach_a_skill.interfaces.executor import IExecutor
from teach_a_skill.interfaces.hardware import IHardwareDetector
from teach_a_skill.interfaces.input_capture import IInputCapture
from teach_a_skill.interfaces.models import IModelProvider, IModelRegistry
from teach_a_skill.interfaces.ocr import IOCREngine
from teach_a_skill.interfaces.platform import IPlatformAdapter
from teach_a_skill.interfaces.privacy import IPrivacyGuard, IPrivacyPolicy
from teach_a_skill.interfaces.recorder import IRecorder
from teach_a_skill.interfaces.screen_capture import IScreenCapture
from teach_a_skill.interfaces.skills import ISkill, ISkillStore
from teach_a_skill.interfaces.speech import ISpeechEngine
from teach_a_skill.interfaces.storage import IStorageManager
from teach_a_skill.interfaces.verifier import IVerifier
from teach_a_skill.interfaces.vision import IVisionEngine
from teach_a_skill.interfaces.window_manager import IWindowManager

__all__ = [
    "IApplication",
    "IPlatformAdapter",
    "IHardwareDetector",
    "IStorageManager",
    "IPrivacyPolicy",
    "IPrivacyGuard",
    "IEvent",
    "IEventSystem",
    "IRecorder",
    "IScreenCapture",
    "IInputCapture",
    "IWindowManager",
    "ISpeechEngine",
    "IVisionEngine",
    "IOCREngine",
    "IModelProvider",
    "IModelRegistry",
    "ISkill",
    "ISkillStore",
    "IExecutor",
    "IVerifier",
]
