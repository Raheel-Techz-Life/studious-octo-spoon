"""Face+hand interaction: a finger-heart pose (hand landmarks only) and a
"blow a kiss" sequence (hand near the mouth, plus a deliberate confirmation
pinch - proximity alone is never enough, per the project brief's explicit
warning against inferring intent from a landmark position alone).

Privacy: this module only ever receives landmark *positions* (see
core/face_recognizer.py's module docstring for why that's a structural
guarantee, not a policy). It does not identify anyone, does not infer
emotion, and keeps no history beyond the current frame's timing state.

The finger-heart trigger reuses core.expressive_signs.ExpressiveEngine
directly (feeding it a synthetic "FingerHeart" gesture label when the
geometric pose matches) rather than writing a fourth hold+cooldown state
machine - that engine's stabilization, cooldown, and heart-pulse rendering
hooks are already built and tested. The kiss sequence is a genuinely
different shape (a joint condition over two landmark sets, not a single
pose label) and gets its own small dwell+cooldown state machine.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import Callable

from core import hand_landmarks as hl
from core.expressive_signs import ExpressiveEngine, ExpressiveSign, ExpressiveSignRegistry, ExpressiveStatus
from core.stabilization import GestureStabilizer, StabilizationConfig

# Standard MediaPipe face mesh topology (478-point): inner upper/lower lip
# center. Used only as a geometric reference point - never to identify,
# classify an expression, or otherwise interpret the face.
MOUTH_UPPER = 13
MOUTH_LOWER = 14


@dataclass
class FaceHandConfig:
    finger_heart_pinch_threshold: float = 0.35  # tighter than Mouse mode's click pinch - a deliberate small loop
    mouth_proximity_threshold: float = 0.18     # normalized distance from index fingertip to mouth center
    kiss_hold_s: float = 0.4                    # how long proximity + pinch must be sustained together
    kiss_cooldown_s: float = 2.0
    heart_float_duration_s: float = 1.8


@dataclass
class FloatingHeart:
    x: float
    y: float
    vy: float  # negative = upward
    scale: float


@dataclass
class FaceHandStatus:
    hand_tracking: bool = False
    face_tracking: bool = False
    finger_heart_status: ExpressiveStatus | None = None
    near_mouth: bool = False
    kiss_progress: float = 0.0  # 0..1 dwell progress toward triggering
    kiss_effect_progress: float = 1.0  # 1.0 = no floating-hearts effect in progress
    floating_hearts: list[FloatingHeart] = field(default_factory=list)


class FaceHandEngine:
    def __init__(self, config: FaceHandConfig | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 rng: random.Random | None = None):
        self.config = config or FaceHandConfig()
        self._clock = clock
        self._rng = rng or random.Random()

        heart_registry = ExpressiveSignRegistry(signs=[
            ExpressiveSign("finger_heart", "FingerHeart", "Finger Heart", "heart", "🫶"),
        ])
        heart_stabilizer = GestureStabilizer(
            StabilizationConfig(stability_duration_s=0.4, cooldown_s=1.5, min_confidence=0.5),
            clock=clock,
        )
        self._heart_engine = ExpressiveEngine(registry=heart_registry, stabilizer=heart_stabilizer,
                                               clock=clock, rng=self._rng)

        self._kiss_candidate_since: float | None = None
        self._kiss_last_trigger: float | None = None
        self._kiss_effect_start: float | None = None
        self._last_t: float | None = None
        self.status = FaceHandStatus()

    def reset(self) -> None:
        self._heart_engine.reset()
        self._kiss_candidate_since = None
        self._kiss_last_trigger = None
        self._kiss_effect_start = None
        self._last_t = None
        self.status = FaceHandStatus()

    def update(self, hand_landmarks: list[tuple[float, float]] | None,
               face_landmarks: list[tuple[float, float]] | None) -> FaceHandStatus:
        now = self._clock()
        dt = (now - self._last_t) if self._last_t is not None else 0.0
        self._last_t = now

        self.status.hand_tracking = hand_landmarks is not None
        self.status.face_tracking = face_landmarks is not None

        is_finger_heart = bool(hand_landmarks) and self._is_finger_heart(hand_landmarks)
        self.status.finger_heart_status = self._heart_engine.update(
            "FingerHeart" if is_finger_heart else None, 1.0 if is_finger_heart else 0.0,
        )

        near, pinching = self._evaluate_kiss_condition(hand_landmarks, face_landmarks)
        self.status.near_mouth = near
        self._update_kiss_dwell(near and pinching, now)
        self._advance_kiss_effect(now, dt)
        return self.status

    def _is_finger_heart(self, lm: list[tuple[float, float]]) -> bool:
        scale = hl.hand_scale(lm)
        if scale <= 1e-6:
            return False
        pinch = hl.distance(lm, hl.THUMB_TIP, hl.INDEX_TIP) / scale
        if pinch >= self.config.finger_heart_pinch_threshold:
            return False
        # The other three fingers stay curled for a finger-heart - this is
        # what tells it apart from an ordinary pinch (e.g. Mouse mode's click).
        return (
            not hl.finger_extended(lm, hl.MIDDLE_TIP, hl.MIDDLE_PIP, hl.MIDDLE_MCP)
            and not hl.finger_extended(lm, hl.RING_TIP, hl.RING_PIP, hl.RING_MCP)
            and not hl.finger_extended(lm, hl.PINKY_TIP, hl.PINKY_PIP, hl.PINKY_MCP)
        )

    def _evaluate_kiss_condition(self, hand_lm, face_lm) -> tuple[bool, bool]:
        if not hand_lm or not face_lm:
            return False, False
        mouth_x = (face_lm[MOUTH_UPPER][0] + face_lm[MOUTH_LOWER][0]) / 2
        mouth_y = (face_lm[MOUTH_UPPER][1] + face_lm[MOUTH_LOWER][1]) / 2
        index_x, index_y = hand_lm[hl.INDEX_TIP]
        near = math.hypot(index_x - mouth_x, index_y - mouth_y) < self.config.mouth_proximity_threshold
        if not near:
            return False, False
        scale = hl.hand_scale(hand_lm)
        pinch = hl.distance(hand_lm, hl.THUMB_TIP, hl.INDEX_TIP) / max(scale, 1e-6)
        pinching = pinch < self.config.finger_heart_pinch_threshold
        return near, pinching

    def _update_kiss_dwell(self, confirmed: bool, now: float) -> None:
        if not confirmed:
            self._kiss_candidate_since = None
            self.status.kiss_progress = 0.0
            return

        if self._kiss_candidate_since is None:
            self._kiss_candidate_since = now

        held_for = now - self._kiss_candidate_since
        self.status.kiss_progress = min(1.0, held_for / self.config.kiss_hold_s)

        in_cooldown = (self._kiss_last_trigger is not None
                       and now - self._kiss_last_trigger < self.config.kiss_cooldown_s)
        if held_for >= self.config.kiss_hold_s and not in_cooldown:
            self._trigger_kiss(now)
            self._kiss_candidate_since = None  # require a fresh hold for the next one

    def _trigger_kiss(self, now: float) -> None:
        self._kiss_last_trigger = now
        self._kiss_effect_start = now
        hearts = []
        for i in range(6):
            hearts.append(FloatingHeart(
                x=0.5 + self._rng.uniform(-0.1, 0.1),
                y=0.55 + self._rng.uniform(-0.05, 0.05),
                vy=-self._rng.uniform(0.12, 0.25),
                scale=self._rng.uniform(0.6, 1.0),
            ))
        self.status.floating_hearts = hearts
        self.status.kiss_effect_progress = 0.0

    def _advance_kiss_effect(self, now: float, dt: float) -> None:
        if self._kiss_effect_start is None:
            self.status.kiss_effect_progress = 1.0
            self.status.floating_hearts = []
            return

        elapsed = now - self._kiss_effect_start
        if elapsed >= self.config.heart_float_duration_s:
            self._kiss_effect_start = None
            self.status.kiss_effect_progress = 1.0
            self.status.floating_hearts = []
            return

        self.status.kiss_effect_progress = elapsed / self.config.heart_float_duration_s
        for heart in self.status.floating_hearts:
            heart.y += heart.vy * dt
