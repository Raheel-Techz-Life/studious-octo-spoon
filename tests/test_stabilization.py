import time

from core.stabilization import GestureStabilizer, StabilizationConfig


def make_stabilizer(stability_s=0.1, cooldown_s=0.2, min_confidence=0.6):
    return GestureStabilizer(StabilizationConfig(
        stability_duration_s=stability_s, cooldown_s=cooldown_s, min_confidence=min_confidence,
    ))


def test_no_fire_below_min_confidence():
    s = make_stabilizer()
    fire, state, latency = s.update("Thumb_Up", 0.3)
    assert fire is None
    assert latency is None


def test_fires_only_after_stability_window():
    s = make_stabilizer(stability_s=0.15)
    fire, _, _ = s.update("Thumb_Up", 0.9)
    assert fire is None  # just started holding, not stable yet
    time.sleep(0.2)
    fire, _, latency = s.update("Thumb_Up", 0.9)
    assert fire == "Thumb_Up"
    assert latency is not None and latency >= 150


def test_does_not_refire_while_held_sustained():
    s = make_stabilizer(stability_s=0.05, cooldown_s=1.0)
    s.update("Thumb_Up", 0.9)  # candidate acquired, stability timer starts now
    time.sleep(0.1)
    fire1, _, _ = s.update("Thumb_Up", 0.9)
    fire2, _, _ = s.update("Thumb_Up", 0.9)  # still held, no time passed since fire1
    assert fire1 == "Thumb_Up"
    assert fire2 is None  # cooldown + already-fired guard both block this


def test_switching_gesture_resets_stability_timer():
    s = make_stabilizer(stability_s=0.15)
    s.update("Thumb_Up", 0.9)
    time.sleep(0.1)
    fire, _, _ = s.update("Victory", 0.9)  # switched before Thumb_Up stabilized
    assert fire is None
    time.sleep(0.2)
    fire, _, _ = s.update("Victory", 0.9)
    assert fire == "Victory"


def test_losing_hand_resets_candidate():
    s = make_stabilizer(stability_s=0.1)
    s.update("Thumb_Up", 0.9)
    s.update(None, 0.0)  # hand disappears
    time.sleep(0.15)
    fire, _, _ = s.update("Thumb_Up", 0.9)
    assert fire is None  # must restart the stability window from scratch


def test_cooldown_blocks_repeat_after_release_and_reacquire():
    s = make_stabilizer(stability_s=0.05, cooldown_s=0.3)
    s.update("Victory", 0.9)  # candidate acquired, stability timer starts now
    time.sleep(0.1)
    fire1, _, _ = s.update("Victory", 0.9)
    assert fire1 == "Victory"
    s.update(None, 0.0)  # release
    time.sleep(0.1)
    fire2, _, _ = s.update("Victory", 0.9)  # re-shown quickly, before cooldown elapses
    assert fire2 is None
