"""Smoke tests for the expressive-sign renderer: never crashes, always
returns a same-shaped frame. Drawing correctness isn't meaningfully
assertable pixel-by-pixel (see test_magic_overlay.py for the same
reasoning applied to Magic Mode's renderer).
"""

import random

import numpy as np

from core.expressive_signs import ExpressiveEngine
from ui.expressive_overlay import draw_expressive_overlay


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


def blank_frame(w=320, h=240):
    return np.zeros((h, w, 3), dtype=np.uint8)


def hold_gesture(engine, clock, gesture, confidence=0.9, frames=6, dt=0.03):
    status = None
    for _ in range(frames):
        clock.advance(dt)
        status = engine.update(gesture, confidence)
    return status


def test_overlay_is_a_no_op_with_no_active_effect():
    engine = ExpressiveEngine()
    status = engine.update(None, 0.0)
    frame = blank_frame()
    out = draw_expressive_overlay(frame, status)
    assert np.array_equal(out, frame)


def test_overlay_draws_confetti_without_error():
    from core.stabilization import GestureStabilizer, StabilizationConfig
    clock = FakeClock()
    stabilizer = GestureStabilizer(StabilizationConfig(
        stability_duration_s=0.1, cooldown_s=0.3, min_confidence=0.6), clock=clock)
    engine = ExpressiveEngine(stabilizer=stabilizer, clock=clock, rng=random.Random(5))
    status = hold_gesture(engine, clock, "Victory")
    frame = blank_frame()
    out = draw_expressive_overlay(frame, status)
    assert out.shape == frame.shape
    assert not np.array_equal(out, frame)


def test_overlay_draws_pulsing_heart_without_error():
    from core.stabilization import GestureStabilizer, StabilizationConfig
    clock = FakeClock()
    stabilizer = GestureStabilizer(StabilizationConfig(
        stability_duration_s=0.1, cooldown_s=0.3, min_confidence=0.6), clock=clock)
    engine = ExpressiveEngine(stabilizer=stabilizer, clock=clock, rng=random.Random(6))
    status = hold_gesture(engine, clock, "ILoveYou")
    frame = blank_frame()
    out = draw_expressive_overlay(frame, status)
    assert out.shape == frame.shape
    assert not np.array_equal(out, frame)
