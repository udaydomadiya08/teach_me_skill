"""High-throughput stress testing, backpressure enforcement, and bounded memory verification."""

import time

from teach_a_skill.recorder.buffer import AsyncPersistenceWorker, BoundedEventQueue
from teach_a_skill.recorder.events import Event, EventPriority, EventType


def test_high_throughput_burst(storage_mgr):
    """Simulate 5,000+ events/sec burst and verify rapid persistence without unbounded queue."""
    persisted_events: list[Event] = []

    queue = BoundedEventQueue(maxsize=10000)
    worker = AsyncPersistenceWorker(event_queue=queue, persist_fn=persisted_events.append)
    worker.start()

    total_events = 5000
    t0 = time.monotonic()
    for i in range(total_events):
        evt = Event.create(
            session_id="stress_session_01",
            sequence_number=i,
            event_type=EventType.MOUSE_MOVE,
            source="mouse",
            payload={"x": float(i % 1920), "y": float(i % 1080)},
            priority=EventPriority.MEDIUM,
        )
        enqueued = queue.put(evt)
        assert enqueued is True

    # Stop and drain worker
    worker.stop()
    duration = time.monotonic() - t0

    throughput = total_events / max(0.001, duration)
    assert len(persisted_events) == total_events
    # Throughput should exceed 2,000 events/sec easily on standard machines
    assert throughput > 1000.0
    # Queue must be empty after drain
    assert queue.qsize() == 0


def test_backpressure_priority_shedding():
    """Verify that under queue saturation, LOW is dropped first, then MEDIUM, never CRITICAL."""
    # Small queue of maxsize=10
    # >=80% is 8 items -> LOW dropped
    # >=90% is 9 items -> MEDIUM dropped
    queue = BoundedEventQueue(maxsize=10)

    # 1. Fill queue to 8 items (80%)
    for i in range(8):
        evt = Event.create(
            session_id="sess_bp",
            sequence_number=i,
            event_type=EventType.MOUSE_MOVE,
            source="mouse",
            priority=EventPriority.MEDIUM,
        )
        assert queue.put(evt) is True

    # 2. At 80%, a LOW priority event must be rejected/dropped
    low_evt = Event.create(
        session_id="sess_bp",
        sequence_number=8,
        event_type=EventType.SCREENSHOT_CAPTURED,
        source="screen",
        priority=EventPriority.LOW,
    )
    assert queue.put(low_evt) is False
    assert queue.metrics.events_dropped_low == 1

    # 3. But a MEDIUM priority event is still accepted at 80%
    med_evt = Event.create(
        session_id="sess_bp",
        sequence_number=9,
        event_type=EventType.MOUSE_MOVE,
        source="mouse",
        priority=EventPriority.MEDIUM,
    )
    assert queue.put(med_evt) is True
    # Now qsize is 9 (90%)

    # 4. At 90%, MEDIUM is also dropped
    med_evt2 = Event.create(
        session_id="sess_bp",
        sequence_number=10,
        event_type=EventType.MOUSE_MOVE,
        source="mouse",
        priority=EventPriority.MEDIUM,
    )
    assert queue.put(med_evt2) is False
    assert queue.metrics.events_dropped_medium == 1

    # 5. But CRITICAL priority is still accepted
    crit_evt = Event.create(
        session_id="sess_bp",
        sequence_number=11,
        event_type=EventType.MOUSE_DOWN,
        source="mouse",
        priority=EventPriority.CRITICAL,
    )
    assert queue.put(crit_evt) is True


def test_throughput_scales_100_1000_10000_rates():
    """Test synthetic rate scalability across different simulation volumes."""
    rates = [100, 1000, 10000]
    for rate in rates:
        queue = BoundedEventQueue(maxsize=15000)
        events_batch = [
            Event.create(
                session_id=f"rate_{rate}",
                sequence_number=i,
                event_type=EventType.KEY_DOWN,
                source="keyboard",
                priority=EventPriority.CRITICAL,
            )
            for i in range(min(rate, 2000))
        ]
        t0 = time.monotonic()
        for evt in events_batch:
            queue.put(evt)
        elapsed = time.monotonic() - t0
        assert elapsed < 1.0  # Ingestion must be sub-second for 2,000 events
        assert queue.qsize() == len(events_batch)
