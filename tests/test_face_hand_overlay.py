"""Smoke tests for the Face+Hand renderer: never crashes, always returns a
same-shaped frame. See test_magic_overlay.py for why drawing correctness
isn't asserted pixel-by-pixel.
"""

import random

import numpy as np

from core.face_hand_interaction import FaceHandConfig, FaceHandEngine, MOUTH_LOWER, MOUTH_UPPER
from ui.face_hand_overlay import draw_face_hand_overlay


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


def blank_frame(w=320, h=240):
    return np.zeros((h, w, 3), dtype=np.uint8)


def make_hand(index=(0.5, 0.5), thumb=(0.5, 0.5)):
    lm = [(0.0, 0.0)] * 21
    lm[0] = (0.5, 0.9)
    lm[4] = thumb
    lm[8] = index
    lm[5], lm[9], lm[13], lm[17] = (0.48, 0.6), (0.5, 0.6), (0.52, 0.6), (0.54, 0.6)
    lm[6], lm[10], lm[14], lm[18] = (0.49, 0.5), (0.5, 0.5), (0.52, 0.5), (0.54, 0.5)
    lm[12], lm[16], lm[20] = (0.5, 0.55), (0.52, 0.55), (0.54, 0.55)  # curled
    return lm


def make_face(mouth=(0.5, 0.5)):
    lm = [(0.0, 0.0)] * 478
    lm[MOUTH_UPPER] = (mouth[0], mouth[1] - 0.005)
    lm[MOUTH_LOWER] = (mouth[0], mouth[1] + 0.005)
    return lm


def test_overlay_is_a_no_op_with_no_active_effect():
    engine = FaceHandEngine()
    status = engine.update(None, None)
    frame = blank_frame()
    out = draw_face_hand_overlay(frame, status)
    assert np.array_equal(out, frame)


def test_overlay_draws_finger_heart_pulse_without_error():
    clock = FakeClock()
    engine = FaceHandEngine(clock=clock, rng=random.Random(1))
    hand = make_hand()
    status = None
    for _ in range(6):
        clock.advance(0.1)
        status = engine.update(hand, None)
    frame = blank_frame()
    out = draw_face_hand_overlay(frame, status)
    assert out.shape == frame.shape
    assert not np.array_equal(out, frame)


def test_overlay_draws_floating_hearts_without_error():
    clock = FakeClock()
    engine = FaceHandEngine(FaceHandConfig(kiss_hold_s=0.2), clock=clock, rng=random.Random(2))
    hand = make_hand()
    face = make_face()
    status = None
    for _ in range(4):
        clock.advance(0.1)
        status = engine.update(hand, face)
    assert status.floating_hearts  # sanity: the effect actually triggered
    frame = blank_frame()
    out = draw_face_hand_overlay(frame, status)
    assert out.shape == frame.shape
    assert not np.array_equal(out, frame)
