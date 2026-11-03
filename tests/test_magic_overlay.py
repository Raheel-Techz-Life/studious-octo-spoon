"""Smoke tests for the Magic Mode renderer. Drawing correctness isn't
meaningfully assertable pixel-by-pixel; what matters is that it never
crashes and always returns a same-shaped frame, across the state machine's
actual output (idle, mid-burst, untracked).
"""

import numpy as np

from core.magic_effects import MagicConfig, MagicEffectState
from ui.magic_overlay import draw_magic_overlay


def make_hand(wrist=(0.5, 0.5)):
    lm = [(0.0, 0.0)] * 21
    lm[0] = wrist
    return lm


def blank_frame(w=320, h=240):
    return np.zeros((h, w, 3), dtype=np.uint8)


def test_overlay_is_a_no_op_when_not_tracking():
    state = MagicEffectState()
    status = state.update(None)
    frame = blank_frame()
    out = draw_magic_overlay(frame, status)
    assert out.shape == frame.shape
    assert np.array_equal(out, frame)  # nothing drawn when no hand is tracked


def test_overlay_runs_without_error_while_idle():
    state = MagicEffectState()
    status = state.update(make_hand((0.4, 0.4)))
    frame = blank_frame()
    out = draw_magic_overlay(frame, status)
    assert out.shape == frame.shape
    assert out.dtype == frame.dtype
    assert not np.array_equal(out, frame)  # the idle ring should have drawn something


def test_overlay_runs_without_error_mid_burst():
    import math
    import random
    from core.dynamic_gestures import DynamicGestureConfig, DynamicGestureDetector

    class FakeClock:
        def __init__(self):
            self.t = 0.0

        def __call__(self):
            return self.t

        def advance(self, dt):
            self.t += dt

    clock = FakeClock()
    detector = DynamicGestureDetector(DynamicGestureConfig(), clock=clock)
    state = MagicEffectState(MagicConfig(), detector=detector, clock=clock, rng=random.Random(1))

    status = None
    for i in range(21):
        frac = i / 20
        angle = -2 * math.pi * frac
        clock.advance(0.05)
        status = state.update(make_hand((0.5 + 0.15 * math.cos(angle), 0.5 + 0.15 * math.sin(angle))))
    assert status.bursting is True

    frame = blank_frame()
    out = draw_magic_overlay(frame, status)
    assert out.shape == frame.shape
    assert not np.array_equal(out, frame)
