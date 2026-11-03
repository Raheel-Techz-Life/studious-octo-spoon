"""Unit tests for trajectory-based swipe/circle detection. Uses a fake
clock instead of real time.sleep() so duration-threshold tests run fast and
deterministically.
"""

import math

from core.dynamic_gestures import (
    CIRCLE_CLOCKWISE,
    CIRCLE_COUNTERCLOCKWISE,
    SWIPE_DOWN,
    SWIPE_LEFT,
    SWIPE_RIGHT,
    SWIPE_UP,
    DynamicGestureConfig,
    DynamicGestureDetector,
)


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def make_hand(wrist=(0.5, 0.5)):
    lm = [(0.0, 0.0)] * 21
    lm[0] = wrist
    return lm


def make_detector(**config_kwargs):
    clock = FakeClock()
    detector = DynamicGestureDetector(DynamicGestureConfig(**config_kwargs), clock=clock)
    return detector, clock


def feed_line(detector, clock, start, end, steps=10, dt=0.03):
    """Feeds a straight-line trajectory from start to end over `steps`
    frames. Returns the first event detected anywhere during the sequence
    (the detector clears its buffer the moment it fires, so a real
    caller - and these tests - must check every frame's return value, not
    just the sequence's last one)."""
    sx, sy = start
    ex, ey = end
    found = None
    for i in range(steps):
        frac = i / (steps - 1)
        x = sx + (ex - sx) * frac
        y = sy + (ey - sy) * frac
        clock.advance(dt)
        event = detector.update(make_hand(wrist=(x, y)))
        if event is not None and found is None:
            found = event
    return found


def feed_circle(detector, clock, center=(0.5, 0.5), radius=0.15, steps=20, dt=0.05, clockwise=True):
    """Feeds a circular trajectory. Image coords: y increases downward, so a
    decreasing angle (standard math convention) traces clockwise on screen.
    Returns the first event detected anywhere during the sequence."""
    cx, cy = center
    found = None
    for i in range(steps + 1):
        frac = i / steps
        angle = (-1 if clockwise else 1) * 2 * math.pi * frac
        x = cx + radius * math.cos(angle)
        y = cy + radius * math.sin(angle)
        clock.advance(dt)
        event = detector.update(make_hand(wrist=(x, y)))
        if event is not None and found is None:
            found = event
    return found


def test_straight_swipe_right_is_detected():
    detector, clock = make_detector()
    event = feed_line(detector, clock, (0.2, 0.5), (0.6, 0.5))
    assert event is not None
    assert event.name == SWIPE_RIGHT


def test_straight_swipe_directions():
    cases = [
        ((0.6, 0.5), (0.2, 0.5), SWIPE_LEFT),
        ((0.5, 0.2), (0.5, 0.6), SWIPE_DOWN),
        ((0.5, 0.6), (0.5, 0.2), SWIPE_UP),
    ]
    for start, end, expected in cases:
        detector, clock = make_detector()
        event = feed_line(detector, clock, start, end)
        assert event is not None, f"expected a swipe for {start}->{end}"
        assert event.name == expected


def test_short_movement_does_not_trigger_a_swipe():
    detector, clock = make_detector()
    event = feed_line(detector, clock, (0.5, 0.5), (0.55, 0.5))  # well under min_distance
    assert event is None


def test_slow_drift_beyond_time_budget_does_not_trigger_a_swipe():
    detector, clock = make_detector()
    # Same distance as a valid swipe, but spread over way more than
    # swipe_max_duration_s - should read as drift, not a deliberate swipe.
    event = feed_line(detector, clock, (0.2, 0.5), (0.6, 0.5), steps=10, dt=0.5)
    assert event is None


def test_wobbly_zigzag_path_does_not_trigger_a_swipe():
    detector, clock = make_detector()
    event = None
    # Net displacement ends up large, but the path doubles back on itself
    # repeatedly, so straightness (net/path-length) should fail the check.
    xs = [0.2, 0.3, 0.22, 0.35, 0.25, 0.4, 0.3, 0.45, 0.35, 0.6]
    for x in xs:
        clock.advance(0.03)
        event = detector.update(make_hand(wrist=(x, 0.5)))
    assert event is None


def test_clockwise_circle_is_detected():
    detector, clock = make_detector()
    event = feed_circle(detector, clock, clockwise=True)
    assert event is not None
    assert event.name == CIRCLE_CLOCKWISE


def test_counterclockwise_circle_is_detected():
    detector, clock = make_detector()
    event = feed_circle(detector, clock, clockwise=False)
    assert event is not None
    assert event.name == CIRCLE_COUNTERCLOCKWISE


def test_partial_circle_below_coverage_threshold_is_not_detected():
    detector, clock = make_detector()
    # A genuine partial arc: only 1/8th of a full rotation (45 degrees),
    # well under the configured 300 degree minimum coverage.
    event = None
    for i in range(6):
        angle = -2 * math.pi * (i / 8) / 6
        clock.advance(0.05)
        event = detector.update(make_hand(wrist=(0.5 + 0.15 * math.cos(angle), 0.5 + 0.15 * math.sin(angle))))
    assert event is None


def test_tiny_radius_circle_is_not_detected():
    detector, clock = make_detector()
    event = feed_circle(detector, clock, radius=0.02, clockwise=True)  # below circle_min_radius
    assert event is None


def test_cooldown_blocks_an_immediate_second_swipe():
    detector, clock = make_detector(cooldown_s=5.0)
    event1 = feed_line(detector, clock, (0.2, 0.5), (0.6, 0.5))
    assert event1 is not None
    event2 = feed_line(detector, clock, (0.6, 0.5), (0.2, 0.5))
    assert event2 is None  # still within the cooldown window


def test_losing_the_hand_mid_swipe_does_not_fire_a_completed_gesture():
    detector, clock = make_detector()
    # Feed half a swipe, then the hand disappears.
    event = None
    for frac in (0.0, 0.1, 0.2):
        clock.advance(0.03)
        x = 0.2 + (0.6 - 0.2) * frac
        event = detector.update(make_hand(wrist=(x, 0.5)))
    assert event is None
    event = detector.update(None)  # hand lost
    assert event is None
    # Even if the hand reappears right where it would have ended up, this
    # must be evaluated as a fresh (too-short) trajectory, not a resumed one.
    clock.advance(0.03)
    event = detector.update(make_hand(wrist=(0.6, 0.5)))
    assert event is None


def test_two_consecutive_swipes_after_cooldown_both_fire():
    detector, clock = make_detector(cooldown_s=0.05)
    event1 = feed_line(detector, clock, (0.2, 0.5), (0.6, 0.5))
    assert event1 is not None
    clock.advance(0.2)  # let the cooldown elapse
    # Start the second swipe from a fresh trajectory: in real use the hand
    # repositions to a new starting point between gestures, so this isn't
    # testing anything the detector's own buffer-clear-on-fire doesn't
    # already guarantee - it just avoids leftover points from the tail of
    # the first feed_line call (which may have kept running after event1
    # fired mid-sequence) skewing the second gesture's measured direction.
    detector.reset()
    event2 = feed_line(detector, clock, (0.6, 0.2), (0.6, 0.6))
    assert event2 is not None
    assert event2.name == SWIPE_DOWN
