"""Unit tests for the expressive-sign registry and trigger engine. Uses a
fake clock for fast, deterministic timing and a seeded RNG for
reproducible particle scatter.
"""

import random

from core.expressive_signs import ExpressiveEngine, ExpressiveSign, ExpressiveSignRegistry
from core.stabilization import GestureStabilizer, StabilizationConfig


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def make_engine(**stab_kwargs):
    clock = FakeClock()
    stab_defaults = dict(stability_duration_s=0.1, cooldown_s=0.3, min_confidence=0.6)
    stab_defaults.update(stab_kwargs)
    # The stabilizer gets the SAME fake clock as the engine, so stability/
    # cooldown timing and effect timing advance together deterministically.
    stabilizer = GestureStabilizer(StabilizationConfig(**stab_defaults), clock=clock)
    engine = ExpressiveEngine(stabilizer=stabilizer, clock=clock, rng=random.Random(7))
    return engine, clock


def hold_gesture(engine, clock, gesture, confidence=0.9, frames=6, dt=0.03):
    """Feeds the same gesture for enough frames/time to pass the
    stabilizer's stability window, returning the final status."""
    status = None
    for _ in range(frames):
        clock.advance(dt)
        status = engine.update(gesture, confidence)
    return status


def test_no_gesture_triggers_nothing():
    engine, clock = make_engine()
    status = hold_gesture(engine, clock, None, confidence=0.0)
    assert status.active_sign_id is None
    assert status.particles == []


def test_held_thumbs_up_triggers_celebrate_with_particles():
    engine, clock = make_engine()
    status = hold_gesture(engine, clock, "Thumb_Up")
    assert status.active_sign_id == "thumbs_up"
    assert status.active_action == "celebrate"
    assert len(status.particles) > 0
    assert status.effect_progress < 1.0


def test_held_victory_triggers_confetti_with_particles():
    engine, clock = make_engine()
    status = hold_gesture(engine, clock, "Victory")
    assert status.active_sign_id == "victory"
    assert status.active_action == "confetti"
    assert len(status.particles) > 0


def test_held_iloveyou_triggers_heart_without_particles():
    engine, clock = make_engine()
    status = hold_gesture(engine, clock, "ILoveYou")
    assert status.active_sign_id == "ily"
    assert status.active_action == "heart"
    assert status.particles == []  # heart is a pulsing shape, not particles
    assert status.effect_progress < 1.0


def test_unmapped_gesture_triggers_nothing():
    engine, clock = make_engine()
    status = hold_gesture(engine, clock, "Open_Palm")  # recognized by the model, but not registered here
    assert status.active_sign_id is None
    assert status.particles == []


def test_holding_the_sign_does_not_retrigger_while_still_in_cooldown():
    engine, clock = make_engine(cooldown_s=5.0)
    status1 = hold_gesture(engine, clock, "Thumb_Up")
    assert status1.active_sign_id == "thumbs_up"
    particles_after_first = list(status1.particles)

    clock.advance(0.05)
    status2 = engine.update("Thumb_Up", 0.9)  # still held, well within cooldown
    assert status2.triggered_at == status1.triggered_at  # no new trigger


def test_disabled_sign_does_not_trigger():
    registry = ExpressiveSignRegistry()
    registry.set_enabled("thumbs_up", False)
    clock = FakeClock()
    stabilizer = GestureStabilizer(StabilizationConfig(
        stability_duration_s=0.1, cooldown_s=0.3, min_confidence=0.6), clock=clock)
    engine = ExpressiveEngine(registry=registry, stabilizer=stabilizer, clock=clock, rng=random.Random(1))
    status = hold_gesture(engine, clock, "Thumb_Up")
    assert status.active_sign_id is None


def test_custom_registered_sign_can_trigger_without_modifying_the_engine():
    registry = ExpressiveSignRegistry(signs=[])
    registry.register(ExpressiveSign("peace_out", "Victory", "Peace Out", "confetti", "✌️"))
    clock = FakeClock()
    stabilizer = GestureStabilizer(StabilizationConfig(
        stability_duration_s=0.1, cooldown_s=0.3, min_confidence=0.6), clock=clock)
    engine = ExpressiveEngine(registry=registry, stabilizer=stabilizer, clock=clock, rng=random.Random(2))
    status = hold_gesture(engine, clock, "Victory")
    assert status.active_sign_id == "peace_out"
    assert status.active_action == "confetti"


def test_confetti_particles_fall_and_spin_over_time():
    engine, clock = make_engine()
    status = hold_gesture(engine, clock, "Victory")
    initial_ys = [p.y for p in status.particles]
    initial_rotations = [p.rotation_deg for p in status.particles]

    clock.advance(0.2)
    status = engine.update(None, 0.0)  # gesture released; effect keeps animating independently

    later_ys = [p.y for p in status.particles]
    later_rotations = [p.rotation_deg for p in status.particles]
    assert any(later > initial for later, initial in zip(later_ys, initial_ys))  # gravity pulled them down
    assert any(later != initial for later, initial in zip(later_rotations, initial_rotations))  # spin


def test_effect_ends_and_clears_particles_after_its_duration():
    clock = FakeClock()
    stabilizer = GestureStabilizer(StabilizationConfig(
        stability_duration_s=0.1, cooldown_s=0.3, min_confidence=0.6), clock=clock)
    engine = ExpressiveEngine(stabilizer=stabilizer, effect_duration_s=0.4,
                               clock=clock, rng=random.Random(3))
    status = hold_gesture(engine, clock, "Thumb_Up")
    assert status.effect_progress < 1.0

    clock.advance(0.5)
    status = engine.update(None, 0.0)
    assert status.effect_progress == 1.0
    assert status.particles == []


def test_hand_loss_does_not_falsely_report_tracking():
    engine, clock = make_engine()
    hold_gesture(engine, clock, "Thumb_Up")
    clock.advance(0.05)
    status = engine.update(None, 0.0)
    assert status.tracking is False
