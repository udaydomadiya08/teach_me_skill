"""Demonstration recorder package."""

from teach_a_skill.recorder.buffer import AsyncPersistenceWorker, BoundedEventQueue
from teach_a_skill.recorder.events import Event, EventPriority, EventType
from teach_a_skill.recorder.keyboard import (
    KeyAction,
    KeyEventPayload,
    ShortcutReconstructor,
)
from teach_a_skill.recorder.mouse import (
    MouseAction,
    MouseButton,
    MouseEventPayload,
    MovementCoalescer,
)
from teach_a_skill.recorder.permissions import (
    PermissionReport,
    PermissionStatus,
    PermissionType,
    PlatformPermissionManager,
)
from teach_a_skill.recorder.recorder import UniversalRecorder
from teach_a_skill.recorder.screen import (
    CaptureProfile,
    DisplayInfo,
    FrameIndexer,
    ScreenFrame,
)
from teach_a_skill.recorder.sensitive import PrivacyFilter, SensitiveInputPolicy
from teach_a_skill.recorder.session import (
    RecordingSession,
    SessionManifest,
    SessionState,
    SessionStateError,
    SessionSummary,
)
from teach_a_skill.recorder.storage import SessionStorage
from teach_a_skill.recorder.window import WindowContext, WindowManagerEngine

__all__ = [
    "UniversalRecorder",
    "RecordingSession",
    "SessionState",
    "SessionStateError",
    "SessionManifest",
    "SessionSummary",
    "Event",
    "EventType",
    "EventPriority",
    "MouseButton",
    "MouseAction",
    "MouseEventPayload",
    "MovementCoalescer",
    "KeyAction",
    "KeyEventPayload",
    "ShortcutReconstructor",
    "PrivacyFilter",
    "SensitiveInputPolicy",
    "CaptureProfile",
    "ScreenFrame",
    "DisplayInfo",
    "FrameIndexer",
    "WindowContext",
    "WindowManagerEngine",
    "BoundedEventQueue",
    "AsyncPersistenceWorker",
    "SessionStorage",
    "PermissionType",
    "PermissionStatus",
    "PermissionReport",
    "PlatformPermissionManager",
]
