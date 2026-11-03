"""Maps stabilized gestures to in-app commands and dispatches them.

Keeps command logic out of the Streamlit layer: app.py calls
GestureController.handle(gesture) and gets back a Command (or None),
regardless of how the UI chooses to render the effect.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from core.event_logger import EventLogger

# Default mapping from the pretrained model's gesture labels to in-app commands.
DEFAULT_MAPPING: dict[str, str] = {
    "Open_Palm": "pause",
    "Thumb_Up": "confirm",
    "Victory": "next",
    "Closed_Fist": "back",
    "ILoveYou": "reset",
}

COMMANDS = ["next", "back", "pause", "confirm", "reset"]


@dataclass
class CommandResult:
    gesture: str
    command: str | None
    status: str  # "executed", "blocked", "unmapped"


class GestureController:
    def __init__(self, event_logger: EventLogger, mapping: dict[str, str] | None = None):
        self.mapping = dict(mapping or DEFAULT_MAPPING)
        self.enabled = True
        self._event_logger = event_logger
        self._handlers: dict[str, Callable[[], None]] = {}

    def register_handler(self, command: str, handler: Callable[[], None]) -> None:
        self._handlers[command] = handler

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled

    def remap(self, gesture: str, command: str) -> None:
        self.mapping[gesture] = command

    def handle(self, gesture: str, latency_ms: float | None = None) -> CommandResult:
        command = self.mapping.get(gesture)
        if command is None:
            return CommandResult(gesture=gesture, command=None, status="unmapped")
        return self.invoke_command(gesture, command, latency_ms=latency_ms)

    def invoke_command(self, gesture_label: str, command: str,
                        latency_ms: float | None = None) -> CommandResult:
        """Dispatches a command directly, bypassing the static gesture->command
        mapping - used by dynamic (motion-based) gestures, which never go
        through `mapping` since they aren't one of the recognizer's discrete
        pose labels. `gesture_label` is only for the event log (e.g.
        "swipe_left"), not looked up anywhere."""
        if not self.enabled:
            self._event_logger.record(gesture_label, command, status="blocked", latency_ms=latency_ms)
            return CommandResult(gesture=gesture_label, command=command, status="blocked")

        handler = self._handlers.get(command)
        if handler is not None:
            handler()

        self._event_logger.record(gesture_label, command, status="executed", latency_ms=latency_ms)
        return CommandResult(gesture=gesture_label, command=command, status="executed")
