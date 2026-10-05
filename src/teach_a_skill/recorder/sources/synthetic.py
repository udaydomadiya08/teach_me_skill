"""Synthetic event generator for deterministic tests, CI runs, and stress benchmarking."""

import threading
import time
from typing import Callable, Optional

from teach_a_skill.recorder.events import Event, EventType
from teach_a_skill.recorder.keyboard import KeyAction, KeyEventPayload
from teach_a_skill.recorder.mouse import MouseAction, MouseButton, MouseEventPayload
from teach_a_skill.recorder.sources.base import BaseEventSource


class SyntheticEventSource(BaseEventSource):
    """Generates realistic, synchronized interaction sequences without needing live OS GUI."""

    def __init__(
        self,
        session_id: str,
        target_event_count: int = 100,
        rate_hz: float = 100.0,  # Events per second (or fast-forward if 0)
        fast_forward: bool = False,
    ) -> None:
        self.session_id = session_id
        self.target_event_count = target_event_count
        self.rate_hz = rate_hz
        self.fast_forward = fast_forward

        self._active = False
        self._thread: Optional[threading.Thread] = None
        self._seq = 1

    @property
    def is_active(self) -> bool:
        return self._active

    def start(self, callback: Callable[[Event], None]) -> None:
        self._active = True
        self._thread = threading.Thread(
            target=self._run_generator,
            args=(callback,),
            name="synthetic-event-source",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._active = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _next_seq(self) -> int:
        s = self._seq
        self._seq += 1
        return s

    def _run_generator(self, callback: Callable[[Event], None]) -> None:
        interval = (1.0 / self.rate_hz) if (not self.fast_forward and self.rate_hz > 0) else 0.0

        # Scripted realistic scenario steps
        steps = [
            ("window", "Finder", "Applications"),
            ("move", 150.0, 200.0),
            ("click", 150.0, 200.0, MouseButton.LEFT),
            ("window", "Google Chrome", "New Tab"),
            ("move", 300.0, 80.0),
            ("click", 300.0, 80.0, MouseButton.LEFT),
            ("text", "h"),
            ("text", "t"),
            ("text", "t"),
            ("text", "p"),
            ("key", "Return", KeyAction.DOWN),
            ("key", "Return", KeyAction.UP),
            ("drag_start", 400.0, 500.0),
            ("drag_move", 450.0, 520.0),
            ("drag_move", 500.0, 550.0),
            ("drag_end", 600.0, 600.0),
            ("shortcut", "c", ["cmd"]),
            ("window", "TextEdit", "Untitled"),
            ("shortcut", "v", ["cmd"]),
        ]

        step_idx = 0
        while self._active and self._seq <= self.target_event_count:
            step = steps[step_idx % len(steps)]
            step_idx += 1

            kind = step[0]

            if kind == "window":
                evt = Event.create(
                    session_id=self.session_id,
                    sequence_number=self._next_seq(),
                    event_type=EventType.WINDOW_FOCUS_CHANGED,
                    source="synthetic",
                    payload={"app_name": step[1], "window_title": step[2]},
                )
            elif kind == "move":
                evt = Event.create(
                    session_id=self.session_id,
                    sequence_number=self._next_seq(),
                    event_type=EventType.MOUSE_MOVE,
                    source="synthetic",
                    payload=MouseEventPayload(
                        x=step[1], y=step[2], action=MouseAction.MOVE
                    ).to_dict(),
                )
            elif kind == "click":
                evt = Event.create(
                    session_id=self.session_id,
                    sequence_number=self._next_seq(),
                    event_type=EventType.MOUSE_CLICK,
                    source="synthetic",
                    payload=MouseEventPayload(
                        x=step[1], y=step[2], action=MouseAction.CLICK, button=step[3]
                    ).to_dict(),
                )
            elif kind == "drag_start":
                evt = Event.create(
                    session_id=self.session_id,
                    sequence_number=self._next_seq(),
                    event_type=EventType.MOUSE_DOWN,
                    source="synthetic",
                    payload=MouseEventPayload(
                        x=step[1],
                        y=step[2],
                        action=MouseAction.DOWN,
                        button=MouseButton.LEFT,
                        is_drag=True,
                    ).to_dict(),
                )
            elif kind == "drag_move":
                evt = Event.create(
                    session_id=self.session_id,
                    sequence_number=self._next_seq(),
                    event_type=EventType.MOUSE_DRAG,
                    source="synthetic",
                    payload=MouseEventPayload(
                        x=step[1],
                        y=step[2],
                        action=MouseAction.DRAG,
                        button=MouseButton.LEFT,
                        is_drag=True,
                    ).to_dict(),
                )
            elif kind == "drag_end":
                evt = Event.create(
                    session_id=self.session_id,
                    sequence_number=self._next_seq(),
                    event_type=EventType.MOUSE_UP,
                    source="synthetic",
                    payload=MouseEventPayload(
                        x=step[1],
                        y=step[2],
                        action=MouseAction.UP,
                        button=MouseButton.LEFT,
                        is_drag=False,
                    ).to_dict(),
                )
            elif kind == "text":
                evt = Event.create(
                    session_id=self.session_id,
                    sequence_number=self._next_seq(),
                    event_type=EventType.TEXT_INPUT,
                    source="synthetic",
                    payload=KeyEventPayload(
                        key=step[1], action=KeyAction.TEXT, text=step[1]
                    ).to_dict(),
                )
            elif kind == "key":
                evt = Event.create(
                    session_id=self.session_id,
                    sequence_number=self._next_seq(),
                    event_type=EventType.KEY_DOWN
                    if step[2] == KeyAction.DOWN
                    else EventType.KEY_UP,
                    source="synthetic",
                    payload=KeyEventPayload(key=step[1], action=step[2]).to_dict(),
                )
            elif kind == "shortcut":
                evt = Event.create(
                    session_id=self.session_id,
                    sequence_number=self._next_seq(),
                    event_type=EventType.KEY_DOWN,
                    source="synthetic",
                    payload=KeyEventPayload(
                        key=step[1],
                        action=KeyAction.DOWN,
                        modifiers=step[2],
                        is_shortcut=True,
                        shortcut_string=f"{step[2][0].capitalize()}+{step[1].upper()}",
                    ).to_dict(),
                )

            callback(evt)

            if interval > 0:
                time.sleep(interval)

        self._active = False
