"""Bounded in-memory event history: recognized gestures and executed commands."""

from __future__ import annotations

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

    def record(self, gesture: str, command: str, status: str = "executed",
               latency_ms: float | None = None) -> None:
        self._events.appendleft(Event(time.time(), gesture, command, status, latency_ms))

    def all(self) -> list[Event]:
        return list(self._events)

    def clear(self) -> None:
        self._events.clear()
