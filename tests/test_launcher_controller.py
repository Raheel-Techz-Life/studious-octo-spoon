"""Unit tests for the launcher's pointer->highlight->pinch-to-launch state
machine. Uses a fake launch function so tests never spawn a real process.
"""

import sys

from core.app_launcher import AppEntry, AppRegistry
from core.launcher_controller import LauncherConfig, LauncherController, grid_rects

# AppEntry.is_available() does a real filesystem/PATH check even in tests
# (that's the whole point - it's the safety gate). sys.executable is an
# absolute path guaranteed to exist on whatever machine runs the test
# suite, so using it as the fake apps' target makes them genuinely
# "available" without depending on any specific app being installed.
_REAL_TARGET = sys.executable


class FakeLaunch:
    def __init__(self, ok: bool = True):
        self.calls: list[str] = []
        self.ok = ok

    def __call__(self, entry: AppEntry):
        self.calls.append(entry.id)
        return self.ok, f"Launched {entry.name}" if self.ok else f"Failed to launch {entry.name}"


def make_hand(index=(0.5, 0.5), thumb=(0.9, 0.9), wrist=(0.5, 0.9)):
    lm = [(0.0, 0.0)] * 21
    lm[0] = wrist
    lm[4] = thumb
    lm[8] = index
    lm[9] = (0.5, 0.6)  # middle MCP, for hand_scale()
    return lm


def make_registry(n=4):
    entries = [AppEntry(f"app{i}", f"App {i}", "x", _REAL_TARGET, platform="any") for i in range(n)]
    return AppRegistry(entries=entries)


def make_controller(n=4, **config_kwargs):
    defaults = dict(mirror_x=False, smoothing_alpha=1.0, confirm_cooldown_s=0.0)
    defaults.update(config_kwargs)
    fake = FakeLaunch()
    controller = LauncherController(make_registry(n), LauncherConfig(**defaults), launch_fn=fake)
    return controller, fake


def tile_center(controller: LauncherController, app_id: str) -> tuple[float, float]:
    entries = controller.registry.visible_entries()
    rects = grid_rects(len(entries))
    for entry, (x0, y0, x1, y1) in zip(entries, rects):
        if entry.id == app_id:
            return ((x0 + x1) / 2, (y0 + y1) / 2)
    raise KeyError(app_id)


_FAR_THUMB = (-1.0, -1.0)


def pinch_release_over(controller: LauncherController, pos: tuple[float, float]) -> None:
    controller.update(make_hand(index=pos, thumb=_FAR_THUMB))
    controller.update(make_hand(index=pos, thumb=pos))
    controller.update(make_hand(index=pos, thumb=_FAR_THUMB))


def test_grid_rects_tile_the_unit_square_without_gaps_for_four_items():
    rects = grid_rects(4, columns=4)
    assert len(rects) == 4
    xs = sorted(r[0] for r in rects)
    assert xs[0] == 0.0
    assert all(0.0 <= v <= 1.0 for r in rects for v in r)


def test_hovering_without_pinching_never_launches():
    controller, fake = make_controller()
    pos = tile_center(controller, "app0")
    for _ in range(10):
        controller.update(make_hand(index=pos, thumb=(0.9, 0.9)))
    assert fake.calls == []


def test_pinch_release_over_app_launches_it_exactly_once():
    controller, fake = make_controller()
    pos = tile_center(controller, "app1")
    pinch_release_over(controller, pos)
    assert fake.calls == ["app1"]
    assert controller.status.last_launched_name == "App 1"
    assert controller.status.last_launch_ok is True


def test_holding_pinch_does_not_relaunch_repeatedly():
    controller, fake = make_controller()
    pos = tile_center(controller, "app2")
    controller.update(make_hand(index=pos, thumb=(0.9, 0.9)))
    controller.update(make_hand(index=pos, thumb=pos))
    for _ in range(10):
        controller.update(make_hand(index=pos, thumb=pos))  # held
    assert fake.calls == []
    controller.update(make_hand(index=pos, thumb=(0.9, 0.9)))  # release
    assert fake.calls == ["app2"]


def test_confirm_cooldown_blocks_an_immediate_second_launch():
    controller, fake = make_controller(confirm_cooldown_s=5.0)
    pos = tile_center(controller, "app0")
    pinch_release_over(controller, pos)
    pinch_release_over(controller, pos)  # within cooldown window
    assert fake.calls == ["app0"]  # second launch suppressed


def test_hand_lost_mid_pinch_does_not_launch():
    controller, fake = make_controller()
    pos = tile_center(controller, "app3")
    controller.update(make_hand(index=pos, thumb=(0.9, 0.9)))
    controller.update(make_hand(index=pos, thumb=pos))  # pinch starts
    controller.update(None)  # hand disappears mid-pinch
    assert fake.calls == []
    assert controller.status.tracking is False


def test_unavailable_app_reports_failure_without_calling_launch_fn():
    # Visible (platform="any", so it appears in the grid) but genuinely
    # unresolvable, to exercise the is_available() gate inside _confirm()
    # rather than the visible_entries() platform filter.
    unavailable = AppEntry("bad", "Bad App", "x", "definitely_not_a_real_exe_xyz123.exe", platform="any")
    registry = AppRegistry(entries=[unavailable])
    fake = FakeLaunch()
    controller = LauncherController(registry, LauncherConfig(mirror_x=False, smoothing_alpha=1.0,
                                                               confirm_cooldown_s=0.0), launch_fn=fake)
    pos = tile_center(controller, "bad")
    pinch_release_over(controller, pos)
    assert fake.calls == []  # never actually invoked for an unavailable target
    assert controller.status.last_launch_ok is False
