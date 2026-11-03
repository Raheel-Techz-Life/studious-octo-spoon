"""Unit tests for the spatial mouse state machine. Uses a FakeActions stub
instead of pyautogui so these tests never move the real OS cursor.
"""

from core.mouse_controller import MouseConfig, MouseController


class FakeActions:
    def __init__(self):
        self.calls: list[tuple] = []

    def move_to(self, x, y):
        self.calls.append(("move_to", x, y))

    def mouse_down(self):
        self.calls.append(("mouse_down",))

    def mouse_up(self):
        self.calls.append(("mouse_up",))

    def click(self):
        self.calls.append(("click",))

    def double_click(self):
        self.calls.append(("double_click",))

    def right_click(self):
        self.calls.append(("right_click",))

    def scroll(self, amount):
        self.calls.append(("scroll", amount))

    def names(self):
        return [c[0] for c in self.calls]


# Each finger's MCP/PIP sit at a fixed spot; "extended" puts the tip far
# from the MCP (beyond pip_dist * 1.15), "curled" puts it close - matching
# exactly what core.hand_landmarks.finger_extended() checks.
_INDEX_MCP, _INDEX_PIP = (0.48, 0.60), (0.49, 0.50)
_MIDDLE_MCP, _MIDDLE_PIP = (0.50, 0.60), (0.50, 0.50)
_RING_MCP, _RING_PIP = (0.52, 0.60), (0.52, 0.50)
_PINKY_MCP, _PINKY_PIP = (0.54, 0.60), (0.54, 0.50)
_EXTENDED_Y, _CURLED_Y = 0.30, 0.55


def _tip(mcp, extended: bool) -> tuple[float, float]:
    return (mcp[0], _EXTENDED_Y) if extended else (mcp[0], _CURLED_Y)


def make_hand(index=(0.5, 0.5), thumb=(0.9, 0.9), wrist=(0.5, 0.9),
              middle_extended=False, ring_extended=False, pinky_extended=False):
    """Builds a 21-point landmark list. `index` and `thumb` are the tip
    positions used directly (for pointer mapping / pinch distance); the
    other fingers are built from extended/curled toggles so scroll-pose
    detection (needs index+middle extended, ring+pinky curled) is
    independent of wherever the test places the index/thumb tips."""
    lm = [(0.0, 0.0)] * 21
    lm[0] = wrist
    lm[4] = thumb
    lm[5], lm[6], lm[8] = _INDEX_MCP, _INDEX_PIP, index
    lm[9], lm[10], lm[12] = _MIDDLE_MCP, _MIDDLE_PIP, _tip(_MIDDLE_MCP, middle_extended)
    lm[13], lm[14], lm[16] = _RING_MCP, _RING_PIP, _tip(_RING_MCP, ring_extended)
    lm[17], lm[18], lm[20] = _PINKY_MCP, _PINKY_PIP, _tip(_PINKY_MCP, pinky_extended)
    return lm


def make_controller(**config_kwargs):
    defaults = dict(region_x0=0.0, region_y0=0.0, region_x1=1.0, region_y1=1.0,
                     mirror_x=False, smoothing_alpha=1.0)
    defaults.update(config_kwargs)
    cfg = MouseConfig(**defaults)
    actions = FakeActions()
    controller = MouseController(config=cfg, actions=actions, screen_size=(1000, 1000))
    return controller, actions


def test_no_hand_does_not_crash_and_marks_not_tracking():
    controller, actions = make_controller()
    status = controller.update(None)
    assert status.tracking is False
    assert actions.calls == []


def test_moving_finger_moves_pointer_every_frame():
    controller, actions = make_controller()
    controller.update(make_hand(index=(0.2, 0.2), thumb=(0.9, 0.9)))
    controller.update(make_hand(index=(0.8, 0.8), thumb=(0.9, 0.9)))
    moves = [c for c in actions.calls if c[0] == "move_to"]
    assert len(moves) == 2
    assert moves[0] != moves[1]


def test_pinch_and_release_fires_exactly_one_click():
    controller, actions = make_controller(drag_hold_s=999)  # effectively disable drag for this test
    controller.update(make_hand(thumb=(0.9, 0.9)))   # not pinched
    controller.update(make_hand(thumb=(0.5, 0.5)))   # pinched (thumb == index)
    controller.update(make_hand(thumb=(0.5, 0.5)))   # still pinched, held
    controller.update(make_hand(thumb=(0.9, 0.9)))   # released
    assert actions.names().count("click") == 1


def test_holding_pinch_does_not_repeat_click():
    controller, actions = make_controller(drag_hold_s=999)
    controller.update(make_hand(thumb=(0.5, 0.5)))
    for _ in range(10):
        controller.update(make_hand(thumb=(0.5, 0.5)))  # held pinch, many frames
    assert actions.names().count("click") == 0  # no click until release
    controller.update(make_hand(thumb=(0.9, 0.9)))
    assert actions.names().count("click") == 1  # exactly one, on release


def test_quick_double_pinch_fires_double_click_not_two_clicks():
    controller, actions = make_controller(drag_hold_s=999, double_click_window_s=5.0)
    controller.update(make_hand(thumb=(0.9, 0.9)))
    controller.update(make_hand(thumb=(0.5, 0.5)))
    controller.update(make_hand(thumb=(0.9, 0.9)))  # first click
    controller.update(make_hand(thumb=(0.5, 0.5)))
    controller.update(make_hand(thumb=(0.9, 0.9)))  # second pinch within window -> double-click
    assert actions.names().count("click") == 1
    assert actions.names().count("double_click") == 1


def test_sustained_pinch_with_movement_becomes_drag():
    import time
    controller, actions = make_controller(drag_hold_s=0.01, drag_move_threshold=0.01)
    # A real drag moves the whole hand (thumb and index together), not just
    # the index tip alone (which would separate the pinch and release it).
    controller.update(make_hand(index=(0.5, 0.5), thumb=(0.5, 0.5)))  # pinch starts
    time.sleep(0.02)
    controller.update(make_hand(index=(0.7, 0.7), thumb=(0.7, 0.7)))  # held + moved together -> drag
    assert "mouse_down" in actions.names()
    controller.update(make_hand(index=(0.9, 0.9), thumb=(0.5, 0.5)))  # thumb/index separate -> release
    assert "mouse_up" in actions.names()
    assert "click" not in actions.names()  # a drag must not also fire a click


def test_right_pinch_fires_single_right_click():
    controller, actions = make_controller()
    controller.update(make_hand(thumb=(0.9, 0.9)))
    # thumb tip must meet the MIDDLE tip (curled by default -> near _MIDDLE_MCP)
    middle_tip = _tip(_MIDDLE_MCP, extended=False)
    controller.update(make_hand(thumb=middle_tip, index=(0.9, 0.9)))
    controller.update(make_hand(thumb=middle_tip, index=(0.9, 0.9)))  # held
    assert actions.names().count("right_click") == 1
    assert "click" not in actions.names()  # right pinch must not also fire a left click


def test_scroll_pose_triggers_scroll_ticks_on_vertical_movement():
    controller, actions = make_controller()
    hand_up = make_hand(index=(0.48, 0.30), middle_extended=True, ring_extended=False, pinky_extended=False)
    controller.update(hand_up)
    hand_moved = make_hand(index=(0.48, 0.10), middle_extended=True, ring_extended=False, pinky_extended=False)
    controller.update(hand_moved)
    assert any(c[0] == "scroll" for c in actions.calls)
    # scrolling must not also move the OS pointer or fire clicks
    assert all(c[0] != "move_to" for c in actions.calls)
    assert all(c[0] != "click" for c in actions.calls)


def test_non_scroll_poses_do_not_trigger_scroll():
    controller, actions = make_controller()
    controller.update(make_hand(index=(0.5, 0.2), thumb=(0.9, 0.9)))  # middle curled (default) -> not scroll pose
    controller.update(make_hand(index=(0.5, 0.1), thumb=(0.9, 0.9)))
    assert all(c[0] != "scroll" for c in actions.calls)


def test_hand_lost_mid_drag_releases_the_button():
    controller, actions = make_controller(drag_hold_s=0.0, drag_move_threshold=0.0)
    controller.update(make_hand(index=(0.5, 0.5), thumb=(0.5, 0.5)))
    controller.update(make_hand(index=(0.6, 0.6), thumb=(0.6, 0.6)))  # moved together -> drag active
    assert "mouse_down" in actions.names()
    controller.update(None)  # hand disappears mid-drag
    assert "mouse_up" in actions.names()  # must not leave the button stuck down


def test_pointer_stays_clamped_when_finger_leaves_active_region():
    controller, actions = make_controller(region_x0=0.2, region_y0=0.2, region_x1=0.8, region_y1=0.8)
    controller.update(make_hand(index=(-5.0, -5.0), thumb=(0.9, 0.9)))  # wildly outside the frame
    move = [c for c in actions.calls if c[0] == "move_to"][0]
    assert 0 <= move[1] <= 1000 and 0 <= move[2] <= 1000  # clamped onto the real screen, not thrown off it
