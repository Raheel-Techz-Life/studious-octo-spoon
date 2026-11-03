"""Expressive hand signs: a small, extensible registry mapping the
GestureRecognizer's static pose labels to celebratory visual effects
(confetti, a pulsing heart), separate from Navigation mode's command
mapping so the same physical gesture can mean something different in each
mode without conflict - e.g. Thumb_Up means "confirm" in Navigation mode
and "celebrate" here.

Reuses core.stabilization.GestureStabilizer (unchanged) for the hold-to-
confirm + cooldown behavior this module needs, rather than re-implementing
it a third time - that logic is already covered by its own test suite;
this module's tests focus on what's new here: registry lookup, effect
triggering, and particle/pulse physics over time.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import Callable

from core.stabilization import GestureStabilizer, StabilizationConfig


@dataclass(frozen=True)
class ExpressiveSign:
    id: str
    gesture_label: str  # the recognizer's pose label that triggers this, e.g. "Thumb_Up"
    display_name: str
    action: str  # "celebrate" | "confetti" | "heart" (rendering hints, see ui/expressive_overlay.py)
    icon: str
    enabled: bool = True


def default_signs() -> list[ExpressiveSign]:
    # Only gestures the bundled MediaPipe model actually recognizes (see
    # core/recognizer.py's SUPPORTED_GESTURES) - no "finger heart" or similar,
    # since that pose isn't in this model's label set and claiming to detect
    # it without verifying would be exactly the overclaim the project brief
    # warns against.
    return [
        ExpressiveSign("thumbs_up", "Thumb_Up", "Thumbs Up", "celebrate", "🎉"),
        ExpressiveSign("victory", "Victory", "Victory Sign", "confetti", "🎊"),
        ExpressiveSign("ily", "ILoveYou", "I-Love-You Sign", "heart", "💖"),
    ]


class ExpressiveSignRegistry:
    """Deliberately small and open-ended: additional signs can be registered
    at runtime without touching this class or any dispatch code elsewhere."""

    def __init__(self, signs: list[ExpressiveSign] | None = None):
        self.signs: list[ExpressiveSign] = signs if signs is not None else default_signs()

    def register(self, sign: ExpressiveSign) -> None:
        self.signs.append(sign)

    def set_enabled(self, sign_id: str, enabled: bool) -> None:
        self.signs = [
            s if s.id != sign_id else ExpressiveSign(s.id, s.gesture_label, s.display_name,
                                                       s.action, s.icon, enabled)
            for s in self.signs
        ]

    def by_gesture_label(self, label: str) -> ExpressiveSign | None:
        return next((s for s in self.signs if s.gesture_label == label and s.enabled), None)


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    color: tuple[int, int, int]
    rotation_deg: float = 0.0
    spin_deg_s: float = 0.0


@dataclass
class ExpressiveStatus:
    tracking: bool = False
    gesture: str | None = None
    confidence: float = 0.0
    stab_progress: float = 0.0
    active_sign_id: str | None = None
    active_action: str | None = None
    triggered_at: float = 0.0
    effect_progress: float = 1.0  # 1.0 = no effect in progress
    particles: list[Particle] = field(default_factory=list)


_CONFETTI_COLORS = [(255, 99, 132), (255, 205, 86), (94, 230, 164), (120, 170, 255), (200, 120, 255)]


class ExpressiveEngine:
    def __init__(self, registry: ExpressiveSignRegistry | None = None,
                 stabilizer: GestureStabilizer | None = None,
                 effect_duration_s: float = 1.5,
                 clock: Callable[[], float] = time.monotonic,
                 rng: random.Random | None = None):
        self.registry = registry or ExpressiveSignRegistry()
        self.stabilizer = stabilizer or GestureStabilizer(
            StabilizationConfig(stability_duration_s=0.6, cooldown_s=1.5, min_confidence=0.6)
        )
        self.effect_duration_s = effect_duration_s
        self._clock = clock
        self._rng = rng or random.Random()
        self._last_t: float | None = None
        self._effect_start: float | None = None
        self.status = ExpressiveStatus()

    def reset(self) -> None:
        self.stabilizer.reset()
        self._last_t = None
        self._effect_start = None
        self.status = ExpressiveStatus()

    def update(self, gesture: str | None, confidence: float) -> ExpressiveStatus:
        now = self._clock()
        dt = (now - self._last_t) if self._last_t is not None else 0.0
        self._last_t = now

        self.status.tracking = gesture is not None
        self.status.gesture = gesture
        self.status.confidence = confidence

        fire, stab_state, _ = self.stabilizer.update(gesture, confidence)
        self.status.stab_progress = stab_state.progress

        if fire is not None:
            sign = self.registry.by_gesture_label(fire)
            if sign is not None:
                self._trigger(sign, now)

        self._advance_effect(now, dt)
        return self.status

    def _trigger(self, sign: ExpressiveSign, now: float) -> None:
        self.status.active_sign_id = sign.id
        self.status.active_action = sign.action
        self.status.triggered_at = now
        self._effect_start = now

        particles: list[Particle] = []
        if sign.action in ("celebrate", "confetti"):
            count = 28
            for i in range(count):
                angle = self._rng.uniform(0, 2 * math.pi)
                speed = self._rng.uniform(0.25, 0.55)
                particles.append(Particle(
                    x=0.5, y=0.75,
                    vx=math.cos(angle) * speed * 0.6,
                    vy=-abs(math.sin(angle)) * speed - 0.15,  # biased upward, like a confetti pop
                    color=self._rng.choice(_CONFETTI_COLORS),
                    rotation_deg=self._rng.uniform(0, 360),
                    spin_deg_s=self._rng.uniform(-240, 240),
                ))
        # "heart" has no particles - the renderer draws a single pulsing
        # heart shape driven by effect_progress instead.
        self.status.particles = particles
        self.status.effect_progress = 0.0

    def _advance_effect(self, now: float, dt: float) -> None:
        if self._effect_start is None:
            self.status.effect_progress = 1.0
            self.status.particles = []
            return

        elapsed = now - self._effect_start
        if elapsed >= self.effect_duration_s:
            self._effect_start = None
            self.status.effect_progress = 1.0
            self.status.particles = []
            return

        self.status.effect_progress = elapsed / self.effect_duration_s
        gravity = 0.9  # normalized units/sec^2, simple downward acceleration for confetti
        for p in self.status.particles:
            p.vy += gravity * dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.rotation_deg = (p.rotation_deg + p.spin_deg_s * dt) % 360.0
