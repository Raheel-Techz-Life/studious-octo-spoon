"""Unit tests for DemoState. The important property this exists for -
being safe to call from a background thread - can't be meaningfully
asserted in a single-threaded test; what's tested here is the ordinary
bounds/reset behavior."""

from core.demo_state import DemoState


def test_next_advances_and_clamps_at_the_last_card():
    state = DemoState(card_count=4)
    state.next()
    state.next()
    assert state.index == 2
    state.next()
    state.next()
    state.next()
    assert state.index == 3  # clamped, not out of range


def test_back_retreats_and_clamps_at_zero():
    state = DemoState(card_count=4)
    state.index = 1
    state.back()
    assert state.index == 0
    state.back()
    assert state.index == 0  # clamped


def test_confirm_sets_the_flag():
    state = DemoState(card_count=4)
    assert state.confirmed is False
    state.confirm()
    assert state.confirmed is True


def test_reset_clears_index_and_confirmed():
    state = DemoState(card_count=4)
    state.index = 2
    state.confirmed = True
    state.reset()
    assert state.index == 0
    assert state.confirmed is False
