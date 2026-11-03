"""Bounded in-memory event history: recognized gestures and executed commands.

Guarded by a lock because, as of the mouse-control engine, this is written
from a background tracking thread and read from Streamlit's render thread.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass


@dataclass
class Event:
    timestamp: float
    gesture: str
    command: str
    status: str  # "executed", "blocked" (paused), "failed"
    latency_ms: float | None = None  # time from first-seen gesture to command fire


class EventLogger:
    def __init__(self, max_events: int = 200):
        self._events: deque[Event] = deque(maxlen=max_events)
        self._lock = threading.Lock()

    def record(self, gesture: str, command: str, status: str = "executed",
               latency_ms: float | None = None) -> None:
        with self._lock:
            self._events.appendleft(Event(time.time(), gesture, command, status, latency_ms))

    def all(self) -> list[Event]:
        with self._lock:
            return list(self._events)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
