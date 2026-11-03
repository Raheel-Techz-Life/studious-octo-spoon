"""Magic Mode's state machine: an idle glow that follows the hand, and a
particle "burst" triggered by a completed circular hand movement.

Deliberately split from rendering (see ui/magic_overlay.py for the actual
drawing): this module only tracks numbers - hand position, rotation phase,
particle positions, burst progress - so the whole animation timeline is
unit-testable with a fake clock, without needing to inspect pixels.

Reuses core.dynamic_gestures.DynamicGestureDetector for circle detection
(the same geometric method Navigation mode's circle gesture uses) rather
than reimplementing motion analysis a second time.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import Callable

from core import hand_landmarks as hl
from core.dynamic_gestures import (
    CIRCLE_CLOCKWISE,
    CIRCLE_COUNTERCLOCKWISE,
    DynamicGestureConfig,
    DynamicGestureDetector,
)


@dataclass
class MagicConfig:
    idle_rotation_speed_deg_s: float = 70.0
    burst_duration_s: float = 1.4
    particle_count: int = 20
    particle_speed: float = 0.35  # normalized units/sec, outward from the burst center
    speed_intensity_scale: float = 6.0  # hand speed -> idle glow intensity multiplier


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float


@dataclass
class MagicStatus:
    tracking: bool = False
    hand_pos: tuple[float, float] | None = None
    idle_phase_deg: float = 0.0
    intensity: float = 0.15  # 0..1, baseline idle glow plus a boost from hand speed
    bursting: bool = False
    burst_progress: float = 0.0  # 0..1 across burst_duration_s
    burst_center: tuple[float, float] | None = None
    particles: list[Particle] = field(default_factory=list)
    last_trigger_direction: str | None = None  # CIRCLE_CLOCKWISE / CIRCLE_COUNTERCLOCKWISE


class MagicEffectState:
    def __init__(self, config: MagicConfig | None = None,
                 detector: DynamicGestureDetector | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 rng: random.Random | None = None):
        self.config = config or MagicConfig()
        self.detector = detector or DynamicGestureDetector(DynamicGestureConfig())
        self._clock = clock
        self._rng = rng or random.Random()
        self._last_pos: tuple[float, float] | None = None
        self._last_t: float | None = None
        self._burst_start: float | None = None
        self.status = MagicStatus()

    def reset(self) -> None:
        self.detector.reset()
        self._last_pos = None
        self._last_t = None
        self._burst_start = None
        self.status = MagicStatus()

    def update(self, landmarks: list[tuple[float, float]] | None) -> MagicStatus:
        now = self._clock()
        dt = (now - self._last_t) if self._last_t is not None else 0.0
        self._last_t = now

        if not landmarks:
            self.reset()
            return self.status

        x, y = landmarks[hl.WRIST]
        self.status.tracking = True
        self.status.hand_pos = (x, y)

        speed = 0.0
        if self._last_pos is not None and dt > 1e-6:
            speed = math.hypot(x - self._last_pos[0], y - self._last_pos[1]) / dt
        self._last_pos = (x, y)

        self.status.intensity = min(1.0, 0.15 + speed * self.config.speed_intensity_scale)
        self.status.idle_phase_deg = (
            self.status.idle_phase_deg + self.config.idle_rotation_speed_deg_s * dt
        ) % 360.0

        event = self.detector.update(landmarks)
        if event is not None and event.name in (CIRCLE_CLOCKWISE, CIRCLE_COUNTERCLOCKWISE):
            self._trigger_burst(x, y, event.name)

        self._advance_burst(now, dt)
        return self.status

    def _trigger_burst(self, x: float, y: float, direction: str) -> None:
        self._burst_start = self._last_t
        self.status.bursting = True
        self.status.burst_progress = 0.0
        self.status.burst_center = (x, y)
        self.status.last_trigger_direction = direction
        particles = []
        for i in range(self.config.particle_count):
            angle = 2 * math.pi * i / self.config.particle_count
            angle += self._rng.uniform(-0.15, 0.15)  # slight scatter so it doesn't look too mechanical
            speed = self.config.particle_speed * self._rng.uniform(0.7, 1.3)
            particles.append(Particle(x, y, math.cos(angle) * speed, math.sin(angle) * speed))
        self.status.particles = particles

    def _advance_burst(self, now: float, dt: float) -> None:
        if self._burst_start is None:
            self.status.bursting = False
            self.status.particles = []
            return

        elapsed = now - self._burst_start
        if elapsed >= self.config.burst_duration_s:
            self._burst_start = None
            self.status.bursting = False
            self.status.burst_progress = 1.0
            self.status.particles = []
            return

        self.status.bursting = True
        self.status.burst_progress = elapsed / self.config.burst_duration_s
        for p in self.status.particles:
            p.x += p.vx * dt
            p.y += p.vy * dt
