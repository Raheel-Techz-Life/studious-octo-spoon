"""Unit tests for the finger-heart and kiss-sequence detectors. Uses a
fake clock for fast, deterministic timing and synthetic hand/face
landmarks - no camera or real model needed.
"""

import random

from core.face_hand_interaction import FaceHandConfig, FaceHandEngine, MOUTH_LOWER, MOUTH_UPPER


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def make_hand(index=(0.5, 0.5), thumb=(0.9, 0.9), ring_curled=True, pinky_curled=True,
              middle_curled=True, wrist=(0.5, 0.9)):
    """A 21-point hand landmark list. Finger curl state is controlled
    directly (same scheme as other tests in this project): tip near MCP =
    curled, tip far from MCP = extended."""
    lm = [(0.0, 0.0)] * 21
    lm[0] = wrist
    lm[4] = thumb
    lm[5], lm[6], lm[8] = (0.48, 0.6), (0.49, 0.5), index
    lm[9] = (0.5, 0.6)  # middle MCP, used by hand_scale()

    def tip(mcp, curled):
        return (mcp[0], 0.55) if curled else (mcp[0], 0.3)

    middle_mcp, ring_mcp, pinky_mcp = (0.5, 0.6), (0.52, 0.6), (0.54, 0.6)
    lm[9], lm[10], lm[12] = middle_mcp, (0.5, 0.5), tip(middle_mcp, middle_curled)
    lm[13], lm[14], lm[16] = ring_mcp, (0.52, 0.5), tip(ring_mcp, ring_curled)
    lm[17], lm[18], lm[20] = pinky_mcp, (0.54, 0.5), tip(pinky_mcp, pinky_curled)
    return lm


def make_face(mouth=(0.5, 0.5)):
    lm = [(0.0, 0.0)] * 478
    lm[MOUTH_UPPER] = (mouth[0], mouth[1] - 0.005)
    lm[MOUTH_LOWER] = (mouth[0], mouth[1] + 0.005)
    return lm


def make_engine(**config_kwargs):
    clock = FakeClock()
    engine = FaceHandEngine(FaceHandConfig(**config_kwargs), clock=clock, rng=random.Random(11))
    return engine, clock


def hold(engine, clock, hand, face, frames=6, dt=0.1):
    status = None
    for _ in range(frames):
        clock.advance(dt)
        status = engine.update(hand, face)
    return status


def test_no_hand_reports_not_tracking_and_no_triggers():
    engine, clock = make_engine()
    status = hold(engine, clock, None, None)
    assert status.hand_tracking is False
    assert status.finger_heart_status.active_sign_id is None
    assert status.floating_hearts == []


def test_finger_heart_pose_triggers_heart_effect():
    engine, clock = make_engine()
    hand = make_hand(index=(0.5, 0.5), thumb=(0.5, 0.5))  # pinched, all other fingers curled (default)
    status = hold(engine, clock, hand, None)
    assert status.finger_heart_status.active_sign_id == "finger_heart"
    assert status.finger_heart_status.active_action == "heart"


def test_pinch_with_extended_fingers_is_not_a_finger_heart():
    engine, clock = make_engine()
    # Same pinch distance, but middle finger extended - an ordinary pinch
    # (like Mouse mode's click), not the finger-heart pose.
    hand = make_hand(index=(0.5, 0.5), thumb=(0.5, 0.5), middle_curled=False)
    status = hold(engine, clock, hand, None)
    assert status.finger_heart_status.active_sign_id is None


def test_finger_heart_does_not_require_a_face():
    engine, clock = make_engine()
    hand = make_hand(index=(0.5, 0.5), thumb=(0.5, 0.5))
    status = hold(engine, clock, hand, None)  # no face landmarks at all
    assert status.finger_heart_status.active_sign_id == "finger_heart"


def test_proximity_alone_without_pinch_never_triggers_a_kiss():
    engine, clock = make_engine()
    face = make_face(mouth=(0.5, 0.5))
    hand = make_hand(index=(0.5, 0.5), thumb=(0.9, 0.9))  # near the mouth, but not pinching
    status = hold(engine, clock, hand, face, frames=10)
    assert status.floating_hearts == []
    assert status.kiss_effect_progress == 1.0


def test_pinch_far_from_mouth_never_triggers_a_kiss():
    engine, clock = make_engine()
    face = make_face(mouth=(0.5, 0.5))
    hand = make_hand(index=(0.05, 0.05), thumb=(0.05, 0.05))  # pinching, but nowhere near the mouth
    status = hold(engine, clock, hand, face, frames=10)
    assert status.floating_hearts == []


def test_sustained_proximity_and_pinch_triggers_floating_hearts():
    engine, clock = make_engine(kiss_hold_s=0.3)
    face = make_face(mouth=(0.5, 0.5))
    hand = make_hand(index=(0.5, 0.5), thumb=(0.5, 0.5))  # near mouth AND pinching
    status = hold(engine, clock, hand, face, frames=6, dt=0.1)
    assert len(status.floating_hearts) > 0
    assert status.kiss_effect_progress < 1.0


def test_releasing_before_hold_duration_does_not_trigger():
    engine, clock = make_engine(kiss_hold_s=1.0)
    face = make_face(mouth=(0.5, 0.5))
    hand = make_hand(index=(0.5, 0.5), thumb=(0.5, 0.5))
    clock.advance(0.2)
    engine.update(hand, face)
    clock.advance(0.2)
    status = engine.update(None, None)  # released early
    assert status.floating_hearts == []


def test_kiss_cooldown_blocks_an_immediate_second_trigger():
    engine, clock = make_engine(kiss_hold_s=0.2, kiss_cooldown_s=5.0)
    face = make_face(mouth=(0.5, 0.5))
    hand = make_hand(index=(0.5, 0.5), thumb=(0.5, 0.5))
    status1 = hold(engine, clock, hand, face, frames=4, dt=0.1)
    assert len(status1.floating_hearts) > 0
    first_hearts = list(status1.floating_hearts)

    # Release and re-confirm quickly, well within the cooldown window.
    clock.advance(0.1)
    engine.update(None, None)
    status2 = hold(engine, clock, hand, face, frames=4, dt=0.1)
    assert status2.floating_hearts == first_hearts  # no new trigger/replacement


def test_floating_hearts_move_upward_over_time():
    engine, clock = make_engine(kiss_hold_s=0.2)
    face = make_face(mouth=(0.5, 0.5))
    hand = make_hand(index=(0.5, 0.5), thumb=(0.5, 0.5))
    status = hold(engine, clock, hand, face, frames=4, dt=0.1)
    initial_ys = [h.y for h in status.floating_hearts]

    clock.advance(0.3)
    status = engine.update(hand, face)
    later_ys = [h.y for h in status.floating_hearts]
    assert all(later < initial for later, initial in zip(later_ys, initial_ys))  # negative vy = upward


def test_kiss_effect_ends_and_clears_after_its_duration():
    engine, clock = make_engine(kiss_hold_s=0.2, heart_float_duration_s=0.5)
    face = make_face(mouth=(0.5, 0.5))
    hand = make_hand(index=(0.5, 0.5), thumb=(0.5, 0.5))
    status = hold(engine, clock, hand, face, frames=4, dt=0.1)
    assert status.kiss_effect_progress < 1.0

    clock.advance(0.6)
    status = engine.update(None, None)
    assert status.kiss_effect_progress == 1.0
    assert status.floating_hearts == []


def test_reset_clears_both_finger_heart_and_kiss_state():
    engine, clock = make_engine(kiss_hold_s=0.2)
    face = make_face(mouth=(0.5, 0.5))
    hand = make_hand(index=(0.5, 0.5), thumb=(0.5, 0.5))
    hold(engine, clock, hand, face, frames=4, dt=0.1)
    engine.reset()
    assert engine.status.hand_tracking is False
    assert engine.status.floating_hearts == []
    assert engine.status.finger_heart_status is None
