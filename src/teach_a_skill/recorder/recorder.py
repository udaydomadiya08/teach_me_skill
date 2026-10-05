"""Universal demonstration recorder implementation."""

import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

from teach_a_skill.core.errors import StorageError
from teach_a_skill.core.logging import get_logger
from teach_a_skill.interfaces.recorder import IRecorder
from teach_a_skill.recorder.buffer import AsyncPersistenceWorker, BoundedEventQueue
from teach_a_skill.recorder.events import Event, EventPriority, EventType
from teach_a_skill.recorder.keyboard import (
    KeyAction,
    KeyEventPayload,
    ShortcutReconstructor,
)
from teach_a_skill.recorder.mouse import (
    MovementCoalescer,
)
from teach_a_skill.recorder.screen import (
    CaptureProfile,
    FrameIndexer,
    ScreenFrame,
)
from teach_a_skill.recorder.sensitive import PrivacyFilter, SensitiveInputPolicy
from teach_a_skill.recorder.session import (
    RecordingSession,
    SessionState,
    SessionSummary,
)
from teach_a_skill.recorder.sources.base import BaseEventSource
from teach_a_skill.recorder.sources.os_source import (
    OSEventSource,
    ScreenCaptureEngine,
)
from teach_a_skill.recorder.sources.synthetic import SyntheticEventSource
from teach_a_skill.recorder.storage import SessionStorage
from teach_a_skill.recorder.window import WindowContext, WindowManagerEngine
from teach_a_skill.storage.manager import StorageManager

logger = get_logger("teach_a_skill.recorder")


class UniversalRecorder(IRecorder):
    """Local, privacy-preserving, synchronized demonstration recorder."""

    def __init__(
        self,
        storage_manager: StorageManager,
        capture_profile: CaptureProfile = CaptureProfile.BALANCED,
        sensitive_policy: SensitiveInputPolicy = SensitiveInputPolicy.RECORD,
        platform_name: str = "unknown",
        architecture: str = "unknown",
        hardware_profile: Optional[dict[str, Any]] = None,
        event_queue_size: int = 10000,
        screen_engine: Optional[Any] = None,
        min_frame_interval_sec: float = 0.25,
    ) -> None:
        self.storage_manager = storage_manager
        self.capture_profile = capture_profile
        self.sensitive_policy = sensitive_policy
        self.platform_name = platform_name
        self.architecture = architecture
        self.hardware_profile = hardware_profile or {}
        self.min_frame_interval_sec = min_frame_interval_sec

        self.privacy_filter = PrivacyFilter(input_policy=sensitive_policy)
        self.mouse_coalescer = MovementCoalescer()
        self.shortcut_reconstructor = ShortcutReconstructor()
        self.window_engine = WindowManagerEngine()
        self.screen_engine = screen_engine or ScreenCaptureEngine()

        self._session: Optional[RecordingSession] = None
        self._session_storage: Optional[SessionStorage] = None
        self._event_queue: Optional[BoundedEventQueue] = None
        self._persistence_worker: Optional[AsyncPersistenceWorker] = None
        self._frame_indexer: Optional[FrameIndexer] = None

        self._active_source: Optional[BaseEventSource] = None
        self._periodic_timer: Optional[threading.Thread] = None
        self._stop_timer_event = threading.Event()

        self._current_sequence = 0
        self._last_event_id: Optional[str] = None
        self._current_window: Optional[WindowContext] = None
        self._frame_counter = 0
        self._last_frame_mono: float = 0.0

        self._lock = threading.Lock()

    @property
    def is_recording(self) -> bool:
        return self._session is not None and self._session.state == SessionState.RECORDING

    @property
    def is_paused(self) -> bool:
        return self._session is not None and self._session.state == SessionState.PAUSED

    @property
    def current_session(self) -> Optional[RecordingSession]:
        return self._session

    def start_recording(
        self,
        session_id: str,
        metadata: Optional[dict[str, Any]] = None,
        use_synthetic_source: bool = False,
        synthetic_event_count: int = 100,
        synthetic_rate_hz: float = 50.0,
    ) -> None:
        """Start demonstration capture session."""
        with self._lock:
            displays = self.screen_engine.get_display_info()
            self._session = RecordingSession(
                session_id=session_id,
                platform_name=self.platform_name,
                architecture=self.architecture,
                hardware_profile=self.hardware_profile,
                capture_profile=str(self.capture_profile),
                display_config=displays,
            )

            self._session_storage = SessionStorage(self.storage_manager, session_id)
            self._session_storage.initialize_session_layout(self._session.manifest)

            self._event_queue = BoundedEventQueue(maxsize=10000)
            self._frame_indexer = FrameIndexer()
            self._current_sequence = 0
            self._frame_counter = 0
            self._last_event_id = None

            # Transition state machine
            self._session.transition_to(SessionState.RECORDING)

            # Start background persistence worker
            self._persistence_worker = AsyncPersistenceWorker(
                event_queue=self._event_queue,
                persist_fn=self._session_storage.append_event,
            )
            self._persistence_worker.start()

            # Record SESSION_STARTED event
            start_evt = self._create_and_enqueue_event(
                event_type=EventType.SESSION_STARTED,
                source="system",
                payload={"metadata": metadata or {}, "displays": displays},
                priority=EventPriority.CRITICAL,
            )

            # Initial screen checkpoint
            self._capture_screen_checkpoint(
                trigger_reason="session_start", triggering_event_id=start_evt.event_id
            )

            # Start periodic screen checkpoint worker if profile requires it
            self._start_periodic_screen_capture()

            # Start event source (synthetic or OS)
            if use_synthetic_source:
                from teach_a_skill.recorder.sources.os_source import SyntheticScreenEngine

                if isinstance(self.screen_engine, ScreenCaptureEngine):
                    self.screen_engine = SyntheticScreenEngine()

                self._active_source = SyntheticEventSource(
                    session_id=session_id,
                    target_event_count=synthetic_event_count,
                    rate_hz=synthetic_rate_hz,
                )
            else:
                self._active_source = OSEventSource(session_id=session_id)

            self._active_source.start(self.ingest_event)

            logger.info(f"● RECORDING active for session: {session_id} [{self.capture_profile}]")

    def pause_recording(self) -> None:
        """Pause active recording."""
        with self._lock:
            if not self.is_recording:
                return

            self._session.transition_to(SessionState.PAUSED)
            self._create_and_enqueue_event(
                event_type=EventType.SESSION_PAUSED,
                source="system",
                priority=EventPriority.CRITICAL,
            )
            self.shortcut_reconstructor.reset()
            logger.info(f"⏸ PAUSED recording for session: {self._session.session_id}")

    def resume_recording(self) -> None:
        """Resume paused recording."""
        with self._lock:
            if not self.is_paused:
                return

            self._session.transition_to(SessionState.RECORDING)
            evt = self._create_and_enqueue_event(
                event_type=EventType.SESSION_RESUMED,
                source="system",
                priority=EventPriority.CRITICAL,
            )
            # Screen checkpoint upon resumption
            self._capture_screen_checkpoint(
                trigger_reason="session_resumed", triggering_event_id=evt.event_id
            )
            logger.info(f"● RECORDING resumed for session: {self._session.session_id}")

    def stop_recording(self) -> str:
        """Stop recording, flush all buffers, compute integrity checksums, and return session path."""
        with self._lock:
            if self._session is None:
                raise StorageError("No active recording session to stop.")

            # Record final stop event
            self._session.transition_to(SessionState.STOPPING)
            stop_evt = self._create_and_enqueue_event(
                event_type=EventType.SESSION_STOPPED,
                source="system",
                priority=EventPriority.CRITICAL,
            )

            # Final screen checkpoint
            self._capture_screen_checkpoint(
                trigger_reason="session_stop", triggering_event_id=stop_evt.event_id
            )

            # Halt event source and periodic timer
            if self._active_source:
                self._active_source.stop()
                self._active_source = None

            self._stop_periodic_screen_capture()

            # Drain queue and stop worker
            if self._persistence_worker:
                self._persistence_worker.stop()
                self._persistence_worker = None

            # Finalize session state machine
            self._session.transition_to(SessionState.COMPLETED)

            # Persist summary, index, and manifest
            summary = self._session.get_summary()
            frame_index = self._frame_indexer.to_index_dict() if self._frame_indexer else {}

            self._session_storage.finalize_session(
                manifest=self._session.manifest,
                summary=summary.to_dict(),
                frame_index=frame_index,
            )

            session_path = str(self._session_storage.session_dir)
            logger.info(f"■ STOPPED recording for session: {self._session.session_id}")
            logger.info(f"Session saved to: {session_path}")

            return session_path

    def cancel_recording(self) -> str:
        """Abort and cancel recording, marking session as ABORTED."""
        with self._lock:
            if self._session is None:
                raise StorageError("No active recording session to cancel.")

            if self._active_source:
                self._active_source.stop()
                self._active_source = None

            self._stop_periodic_screen_capture()

            self._create_and_enqueue_event(
                event_type=EventType.SESSION_ABORTED,
                source="system",
                priority=EventPriority.CRITICAL,
            )

            if self._persistence_worker:
                self._persistence_worker.stop()
                self._persistence_worker = None

            self._session.transition_to(SessionState.ABORTED)

            summary = self._session.get_summary()
            self._session_storage.finalize_session(
                manifest=self._session.manifest,
                summary=summary.to_dict(),
                frame_index={},
            )

            session_path = str(self._session_storage.session_dir)
            logger.warning(f"Session {self._session.session_id} cancelled and marked ABORTED.")
            return session_path

    def ingest_event(self, event: Event) -> bool:
        """Ingest, filter, and buffer an incoming raw event."""
        if not self.is_recording:
            return False

        # 1. Update window context if window focus event
        if event.event_type == EventType.WINDOW_FOCUS_CHANGED:
            p = event.payload
            self._current_window = WindowContext(
                app_name=p.get("app_name"),
                app_id=p.get("app_id"),
                process_id=p.get("process_id"),
                window_title=p.get("window_title"),
                bounds=p.get("bounds"),
                window_id=p.get("window_id"),
                capability="available",
            )
            # Screen checkpoint on window focus change
            self._capture_screen_checkpoint(
                trigger_reason="window_change", triggering_event_id=event.event_id
            )

        # 2. Apply privacy filter for keyboard events
        if event.event_type in (EventType.KEY_DOWN, EventType.KEY_UP, EventType.TEXT_INPUT):
            app_name = self._current_window.app_name if self._current_window else None
            win_title = self._current_window.window_title if self._current_window else None

            payload_obj = KeyEventPayload(
                key=event.payload.get("key", ""),
                action=KeyAction(event.payload.get("action", "DOWN")),
                code=event.payload.get("code"),
                modifiers=event.payload.get("modifiers", []),
                is_shortcut=event.payload.get("is_shortcut", False),
                shortcut_string=event.payload.get("shortcut_string"),
                text=event.payload.get("text"),
            )
            filtered = self.privacy_filter.filter_key_payload(payload_obj, app_name, win_title)
            if filtered is None:
                # Suppressed by privacy policy!
                return False

            # Update event payload with filtered representation
            event = Event(
                event_id=event.event_id,
                session_id=event.session_id,
                sequence_number=event.sequence_number,
                timestamp=event.timestamp,
                monotonic_timestamp=event.monotonic_timestamp,
                event_type=event.event_type,
                priority=event.priority,
                source=event.source,
                payload=filtered.to_dict(),
            )

        # 3. Mouse trigger detection (trigger checkpoint on click or drag start)
        if event.event_type in (
            EventType.MOUSE_CLICK,
            EventType.MOUSE_DOUBLE_CLICK,
            EventType.MOUSE_DOWN,
        ):
            self._capture_screen_checkpoint(
                trigger_reason="mouse_click", triggering_event_id=event.event_id
            )

        # 4. Enqueue event for persistence
        if self._event_queue:
            enqueued = self._event_queue.put(event)
            if enqueued and self._session:
                app = self._current_window.app_name if self._current_window else None
                self._session.record_event_metric(str(event.event_type), app)
                self._last_event_id = event.event_id
            return enqueued

        return False

    def _create_and_enqueue_event(
        self,
        event_type: EventType,
        source: str,
        payload: Optional[dict[str, Any]] = None,
        priority: Optional[EventPriority] = None,
    ) -> Event:
        self._current_sequence += 1
        evt = Event.create(
            session_id=self._session.session_id,
            sequence_number=self._current_sequence,
            event_type=event_type,
            source=source,
            payload=payload or {},
            priority=priority,
        )
        if self._event_queue:
            self._event_queue.put(evt)
        if self._session:
            app = self._current_window.app_name if self._current_window else None
            self._session.record_event_metric(str(evt.event_type), app)
            self._last_event_id = evt.event_id
        return evt

    def _capture_screen_checkpoint(
        self,
        trigger_reason: str,
        triggering_event_id: Optional[str] = None,
    ) -> None:
        """Capture and persist screen checkpoint frame."""
        if not self.is_recording and trigger_reason != "session_stop":
            return

        app_name = self._current_window.app_name if self._current_window else None
        win_title = self._current_window.window_title if self._current_window else None
        if self.privacy_filter.should_suppress_screen_capture(app_name, win_title):
            # Suppress frame in sensitive applications/windows
            return

        self._frame_counter += 1
        frame_id = f"frame_{self._frame_counter:06d}"
        now_utc = datetime.now(timezone.utc).isoformat()
        mono = time.monotonic()

        if trigger_reason not in ("session_start", "session_stop"):
            if mono - self._last_frame_mono < self.min_frame_interval_sec:
                return

        self._last_frame_mono = mono

        # Capture raw frame bytes
        raw_png = self.screen_engine.capture_frame(display_id=1)

        frame = ScreenFrame(
            frame_id=frame_id,
            timestamp=now_utc,
            monotonic_timestamp=mono,
            display_id=1,
            width=1920,
            height=1080,
            scale_factor=2.0 if self.platform_name == "macos" else 1.0,
            trigger_reason=trigger_reason,
            triggering_event_id=triggering_event_id,
            previous_event_id=self._last_event_id,
            next_event_id=None,
            image_format="png",
            image_bytes=raw_png,
        )

        if self._session_storage:
            self._session_storage.save_frame(frame)

        if self._frame_indexer:
            self._frame_indexer.register_frame(frame)

        if self._session:
            self._session.record_frame_metric(frame_id, trigger_reason)

    def _start_periodic_screen_capture(self) -> None:
        """Start sparse periodic screen checkpoint worker thread."""
        interval = 0.0
        if self.capture_profile == CaptureProfile.BALANCED:
            interval = 3.0
        elif self.capture_profile == CaptureProfile.HIGH:
            interval = 1.0

        if interval <= 0:
            return  # MINIMAL profile: event-triggered only

        self._stop_timer_event.clear()
        self._periodic_timer = threading.Thread(
            target=self._periodic_loop,
            args=(interval,),
            name="periodic-screen-capture",
            daemon=True,
        )
        self._periodic_timer.start()

    def _stop_periodic_screen_capture(self) -> None:
        self._stop_timer_event.set()
        if self._periodic_timer and self._periodic_timer.is_alive():
            self._periodic_timer.join(timeout=1.5)
            self._periodic_timer = None

    def _periodic_loop(self, interval: float) -> None:
        while not self._stop_timer_event.is_set():
            time.sleep(interval)
            if self.is_recording:
                self._capture_screen_checkpoint(trigger_reason="periodic")

    def get_summary(self) -> Optional[SessionSummary]:
        return self._session.get_summary() if self._session else None
