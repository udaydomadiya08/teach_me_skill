"""Event sources package for demonstration recorder."""

from teach_a_skill.recorder.sources.base import BaseEventSource
from teach_a_skill.recorder.sources.os_source import (
    OSEventSource,
    ScreenCaptureEngine,
    SyntheticScreenEngine,
)
from teach_a_skill.recorder.sources.synthetic import SyntheticEventSource

__all__ = [
    "BaseEventSource",
    "SyntheticEventSource",
    "OSEventSource",
    "ScreenCaptureEngine",
    "SyntheticScreenEngine",
]
