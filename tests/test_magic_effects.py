"""Unit tests for Magic Mode's state machine (not its rendering - see
core/magic_effects.py's module docstring for why those are split). Uses a
fake clock for fast, deterministic timing, and a seeded RNG so particle
scatter is reproducible.
"""

import math
import random

from core.dynamic_gestures import DynamicGestureConfig, DynamicGestureDetector
from core.magic_effects import MagicConfig, MagicEffectState


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


def make_state(**config_kwargs):
    clock = FakeClock()
    detector = DynamicGestureDetector(DynamicGestureConfig(), clock=clock)
    state = MagicEffectState(MagicConfig(**config_kwargs), detector=detector,
                              clock=clock, rng=random.Random(42))
    return state, clock


def feed_circle(state, clock, center=(0.5, 0.5), radius=0.15, steps=20, dt=0.05, clockwise=True):
    cx, cy = center
    status = None
    for i in range(steps + 1):
        frac = i / steps
        angle = (-1 if clockwise else 1) * 2 * math.pi * frac
        x = cx + radius * math.cos(angle)
        y = cy + radius * math.sin(angle)
        clock.advance(dt)
        status = state.update(make_hand(wrist=(x, y)))
    return status


def test_no_hand_reports_not_tracking():
    state, clock = make_state()
    status = state.update(None)
    assert status.tracking is False
    assert status.hand_pos is None


def test_tracked_hand_sets_position():
    state, clock = make_state()
    clock.advance(0.03)
    status = state.update(make_hand(wrist=(0.3, 0.4)))
    assert status.tracking is True
    assert status.hand_pos == (0.3, 0.4)


def test_idle_rotation_advances_over_time():
    state, clock = make_state(idle_rotation_speed_deg_s=90.0)
    clock.advance(0.1)
    state.update(make_hand(wrist=(0.5, 0.5)))
    clock.advance(1.0)  # at 90 deg/s, 1s should add ~90 degrees
    status = state.update(make_hand(wrist=(0.5, 0.5)))
    assert 80.0 < status.idle_phase_deg < 100.0


def test_fast_hand_movement_raises_intensity_above_baseline():
    state, clock = make_state()
    clock.advance(0.03)
    state.update(make_hand(wrist=(0.2, 0.2)))
    clock.advance(0.03)
    status = state.update(make_hand(wrist=(0.8, 0.8)))  # large jump in one frame -> high speed
    assert status.intensity > 0.5


def test_stationary_hand_stays_near_baseline_intensity():
    state, clock = make_state()
    for _ in range(5):
        clock.advance(0.03)
        status = state.update(make_hand(wrist=(0.5, 0.5)))  # never moves
    assert status.intensity <= 0.2


def test_completed_circle_triggers_a_burst_with_particles():
    state, clock = make_state(particle_count=16)
    status = feed_circle(state, clock)
    assert status.bursting is True
    assert len(status.particles) == 16
    assert status.burst_center is not None
    assert status.last_trigger_direction is not None


def test_straight_line_motion_does_not_trigger_a_burst():
    state, clock = make_state()
    status = None
    for i in range(10):
        clock.advance(0.03)
        status = state.update(make_hand(wrist=(0.2 + i * 0.04, 0.5)))
    assert status.bursting is False
    assert status.particles == []


def test_particles_move_outward_from_burst_center_over_time():
    state, clock = make_state(particle_count=8, particle_speed=0.5)
    status = feed_circle(state, clock)
    center = status.burst_center
    initial_distances = [math.hypot(p.x - center[0], p.y - center[1]) for p in status.particles]

    clock.advance(0.1)
    status = state.update(make_hand(wrist=center))  # hand stays put; only particles should move
    later_distances = [math.hypot(p.x - center[0], p.y - center[1]) for p in status.particles]

    assert all(later > initial for later, initial in zip(later_distances, initial_distances))


def test_burst_ends_and_clears_particles_after_its_duration():
    state, clock = make_state(burst_duration_s=0.5)
    status = feed_circle(state, clock)
    assert status.bursting is True

    clock.advance(0.6)
    status = state.update(make_hand(wrist=(0.5, 0.5)))
    assert status.bursting is False
    assert status.particles == []
    assert status.burst_progress == 1.0


def test_burst_progress_increases_monotonically_during_the_burst():
    state, clock = make_state(burst_duration_s=1.0)
    status = feed_circle(state, clock)
    progress_values = [status.burst_progress]
    for _ in range(4):
        clock.advance(0.2)
        status = state.update(make_hand(wrist=(0.5, 0.5)))
        progress_values.append(status.burst_progress)
    assert progress_values == sorted(progress_values)
    assert progress_values[-1] <= 1.0


def test_losing_the_hand_mid_burst_clears_everything():
    state, clock = make_state()
    status = feed_circle(state, clock)
    assert status.bursting is True

    status = state.update(None)
    assert status.tracking is False
    assert status.bursting is False
    assert status.particles == []


def test_reset_clears_burst_and_tracking_state():
    state, clock = make_state()
    feed_circle(state, clock)
    state.reset()
    assert state.status.tracking is False
    assert state.status.bursting is False
    assert state.status.particles == []
