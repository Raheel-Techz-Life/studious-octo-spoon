"""Gesture stabilization: requires a gesture to hold steady before it fires,
then enforces a cooldown before the same gesture can fire again.

This is GestureBridge's distinctive feature. Without it, a single sustained
gesture would re-trigger its command on every frame (10+ times/sec).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable


@dataclass
class StabilizationConfig:
    stability_duration_s: float = 0.5   # how long a gesture must hold steady
    cooldown_s: float = 1.0             # minimum gap between repeat triggers
    min_confidence: float = 0.6         # ignore low-confidence predictions


@dataclass
class StabilizationState:
    """Read-only snapshot for the UI to render stabilization progress."""
    candidate_gesture: str | None
    progress: float          # 0.0-1.0 toward stabilizing the candidate
    is_stable: bool          # candidate has met the stability duration
    in_cooldown: bool
    cooldown_remaining_s: float


class GestureStabilizer:
    """Feed it every recognized gesture; it tells you when to actually fire a command."""

    def __init__(self, config: StabilizationConfig | None = None,
                 clock: Callable[[], float] = time.monotonic):
        self.config = config or StabilizationConfig()
        self._clock = clock
        self._candidate: str | None = None
        self._candidate_since: float | None = None
        self._last_fired_gesture: str | None = None
        self._last_fired_at: float | None = None
        self._already_fired_for_candidate = False

    def update(self, gesture: str | None, confidence: float) -> tuple[str | None, StabilizationState, float | None]:
        """Call once per frame. Returns (gesture_to_execute_or_None, state_for_ui, latency_ms)."""
        now = self._clock()

        if gesture is None or confidence < self.config.min_confidence:
            self._reset_candidate()
            return None, self._snapshot(now), None

        if gesture != self._candidate:
            self._candidate = gesture
            self._candidate_since = now
            self._already_fired_for_candidate = False

        held_for = now - (self._candidate_since or now)
        is_stable = held_for >= self.config.stability_duration_s

        since_last_fire = (now - self._last_fired_at) if self._last_fired_at is not None else float("inf")
        in_cooldown = since_last_fire < self.config.cooldown_s

        fire = None
        latency_ms = None
        if is_stable and not self._already_fired_for_candidate and not in_cooldown:
            fire = gesture
            latency_ms = held_for * 1000.0
            self._already_fired_for_candidate = True
            self._last_fired_gesture = gesture
            self._last_fired_at = now

        return fire, self._snapshot(now), latency_ms

    def reset(self) -> None:
        self._reset_candidate()
        self._last_fired_gesture = None
        self._last_fired_at = None

    def _reset_candidate(self) -> None:
        self._candidate = None
        self._candidate_since = None
        self._already_fired_for_candidate = False

    def _snapshot(self, now: float) -> StabilizationState:
        held_for = now - self._candidate_since if self._candidate_since else 0.0
        progress = min(1.0, held_for / self.config.stability_duration_s) if self._candidate else 0.0
        is_stable = progress >= 1.0
        since_last_fire = (now - self._last_fired_at) if self._last_fired_at is not None else float("inf")
        in_cooldown = since_last_fire < self.config.cooldown_s
        return StabilizationState(
            candidate_gesture=self._candidate,
            progress=progress,
            is_stable=is_stable,
            in_cooldown=in_cooldown,
            cooldown_remaining_s=max(0.0, self.config.cooldown_s - since_last_fire),
        )
