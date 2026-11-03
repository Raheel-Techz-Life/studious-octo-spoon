"""Spatial mouse: maps the index fingertip to the OS pointer and turns
pinch/pose gestures into click, double-click, right-click, drag, and scroll.

The actual OS calls (move/click/drag/scroll) go through a small `MouseActions`
interface rather than calling pyautogui directly, so the click/drag/scroll
state machine can be unit-tested without moving the real cursor.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol

from core import hand_landmarks as hl
from core.pointer_filter import ExponentialSmoother


class MouseActions(Protocol):
    def move_to(self, x: int, y: int) -> None: ...
    def mouse_down(self) -> None: ...
    def mouse_up(self) -> None: ...
    def click(self) -> None: ...
    def double_click(self) -> None: ...
    def right_click(self) -> None: ...
    def scroll(self, amount: int) -> None: ...


class PyAutoGuiActions:
    """Real OS pointer control. Imported lazily so the rest of the module
    (and its tests) work on a machine/CI without a display."""

    def __init__(self):
        import pyautogui
        pyautogui.FAILSAFE = True  # moving the real cursor to a screen corner aborts, as a safety net
        pyautogui.PAUSE = 0
        self._pg = pyautogui

    def move_to(self, x: int, y: int) -> None:
        self._pg.moveTo(x, y)

    def mouse_down(self) -> None:
        self._pg.mouseDown()

    def mouse_up(self) -> None:
        self._pg.mouseUp()

    def click(self) -> None:
        self._pg.click()

    def double_click(self) -> None:
        self._pg.doubleClick()

    def right_click(self) -> None:
        self._pg.rightClick()

    def scroll(self, amount: int) -> None:
        self._pg.scroll(amount)


@dataclass
class MouseConfig:
    sensitivity: float = 1.0  # reserved multiplier on mapped movement, for future use
    smoothing_alpha: float = 0.4
    mirror_x: bool = True  # mirrored by default: moving your hand right moves the pointer right, facing the camera
    # Active region: a sub-rectangle of the camera frame (normalized 0-1)
    # that maps to the full screen. A smaller region = less hand travel
    # needed to cross the screen (effectively higher sensitivity).
    region_x0: float = 0.15
    region_y0: float = 0.15
    region_x1: float = 0.85
    region_y1: float = 0.85
    pinch_threshold: float = 0.45  # thumb-index distance / hand_scale below this = pinched
    right_pinch_threshold: float = 0.45  # thumb-middle distance / hand_scale
    drag_hold_s: float = 0.35  # how long a pinch must be held before it becomes a drag
    drag_move_threshold: float = 0.03  # normalized screen-space movement that confirms a drag
    double_click_window_s: float = 0.4
    double_click_distance: float = 0.06  # normalized screen-space distance
    scroll_sensitivity: float = 1200.0  # scroll ticks per normalized unit of vertical movement
    scroll_deadzone: float = 0.004  # ignore vertical jitter smaller than this per frame
    click_enabled: bool = True
    right_click_enabled: bool = True
    drag_enabled: bool = True
    scroll_enabled: bool = True


@dataclass
class MouseStatus:
    tracking: bool = False
    pointer_norm: tuple[float, float] | None = None  # smoothed, region-mapped, pre-screen-scale
    state: str = "idle"  # idle | pinched | dragging | scrolling
    last_action: str | None = None
    last_action_at: float = 0.0


class MouseController:
    def __init__(self, config: MouseConfig | None = None, actions: MouseActions | None = None,
                 screen_size: tuple[int, int] | None = None):
        self.config = config or MouseConfig()
        self.actions = actions or PyAutoGuiActions()
        if screen_size is not None:
            self.screen_w, self.screen_h = screen_size
        else:
            import pyautogui
            self.screen_w, self.screen_h = pyautogui.size()

        self._smoother = ExponentialSmoother(self.config.smoothing_alpha)
        self.status = MouseStatus()

        self._primary_pinched = False
        self._pinch_start_time = 0.0
        self._pinch_start_pos: tuple[float, float] | None = None
        self._dragging = False

        self._right_pinched = False

        self._last_click_time = 0.0
        self._last_click_pos: tuple[float, float] | None = None

        self._scrolling = False
        self._last_scroll_y: float | None = None

    def set_smoothing(self, alpha: float) -> None:
        self.config.smoothing_alpha = alpha
        self._smoother.alpha = alpha

    def reset(self) -> None:
        """Release any held mouse button and clear transient state - call this
        whenever mouse mode is paused, disabled, or tracking is lost, so a
        held pinch never leaves the real mouse button stuck down."""
        if self._dragging:
            self.actions.mouse_up()
        self._primary_pinched = False
        self._dragging = False
        self._right_pinched = False
        self._scrolling = False
        self._last_scroll_y = None
        self._smoother.reset()
        self.status = MouseStatus()

    def update(self, landmarks: list[tuple[float, float]] | None) -> MouseStatus:
        now = time.monotonic()
        cfg = self.config

        if not landmarks:
            # Hand lost: stop issuing new actions and release any held button,
            # rather than leaving a drag stuck or the pointer frozen mid-gesture.
            self.reset()
            self.status.tracking = False
            return self.status

        self.status.tracking = True
        scale = hl.hand_scale(landmarks)
        if scale <= 1e-6:
            return self.status

        index_x, index_y = landmarks[hl.INDEX_TIP]
        if cfg.mirror_x:
            index_x = 1.0 - index_x

        region_w = max(1e-6, cfg.region_x1 - cfg.region_x0)
        region_h = max(1e-6, cfg.region_y1 - cfg.region_y0)
        norm_x = min(1.0, max(0.0, (index_x - cfg.region_x0) / region_w))
        norm_y = min(1.0, max(0.0, (index_y - cfg.region_y0) / region_h))

        smooth_x, smooth_y = self._smoother.update(norm_x, norm_y)
        self.status.pointer_norm = (smooth_x, smooth_y)

        screen_x = int(smooth_x * self.screen_w)
        screen_y = int(smooth_y * self.screen_h)

        scroll_pose = (
            cfg.scroll_enabled
            and hl.finger_extended(landmarks, hl.INDEX_TIP, hl.INDEX_PIP, hl.INDEX_MCP)
            and hl.finger_extended(landmarks, hl.MIDDLE_TIP, hl.MIDDLE_PIP, hl.MIDDLE_MCP)
            and not hl.finger_extended(landmarks, hl.RING_TIP, hl.RING_PIP, hl.RING_MCP)
            and not hl.finger_extended(landmarks, hl.PINKY_TIP, hl.PINKY_PIP, hl.PINKY_MCP)
        )

        if scroll_pose:
            self._update_scroll(smooth_y, now)
            self.status.state = "scrolling"
            return self.status
        elif self._scrolling:
            self._scrolling = False
            self._last_scroll_y = None

        self.actions.move_to(screen_x, screen_y)

        pinch_dist = hl.distance(landmarks, hl.THUMB_TIP, hl.INDEX_TIP) / scale
        is_pinched = pinch_dist < cfg.pinch_threshold

        if cfg.right_click_enabled:
            right_dist = hl.distance(landmarks, hl.THUMB_TIP, hl.MIDDLE_TIP) / scale
            is_right_pinched = right_dist < cfg.right_pinch_threshold
            if is_right_pinched and not self._right_pinched and not self._primary_pinched:
                self.actions.right_click()
                self._set_action("right_click", now)
            self._right_pinched = is_right_pinched

        if cfg.click_enabled:
            self._update_primary_pinch(is_pinched, smooth_x, smooth_y, now)
        self.status.state = "dragging" if self._dragging else ("pinched" if self._primary_pinched else "idle")
        return self.status

    def _update_primary_pinch(self, is_pinched: bool, x: float, y: float, now: float) -> None:
        cfg = self.config
        if is_pinched and not self._primary_pinched:
            self._primary_pinched = True
            self._pinch_start_time = now
            self._pinch_start_pos = (x, y)
            self._dragging = False

        elif is_pinched and self._primary_pinched and not self._dragging and cfg.drag_enabled:
            held_for = now - self._pinch_start_time
            sx, sy = self._pinch_start_pos or (x, y)
            moved = ((x - sx) ** 2 + (y - sy) ** 2) ** 0.5
            if held_for >= cfg.drag_hold_s and moved >= cfg.drag_move_threshold:
                self._dragging = True
                self.actions.mouse_down()
                self._set_action("drag_start", now)

        elif not is_pinched and self._primary_pinched:
            if self._dragging:
                self.actions.mouse_up()
                self._set_action("drag_end", now)
                self._dragging = False
            else:
                since_last = now - self._last_click_time
                last_pos = self._last_click_pos
                dist = (((x - last_pos[0]) ** 2 + (y - last_pos[1]) ** 2) ** 0.5) if last_pos else 999.0
                if since_last <= cfg.double_click_window_s and dist <= cfg.double_click_distance:
                    self.actions.double_click()
                    self._set_action("double_click", now)
                    self._last_click_time = 0.0  # consumed; a third quick pinch starts fresh
                    self._last_click_pos = None
                else:
                    self.actions.click()
                    self._set_action("click", now)
                    self._last_click_time = now
                    self._last_click_pos = (x, y)
            self._primary_pinched = False

    def _update_scroll(self, y: float, now: float) -> None:
        if self._last_scroll_y is None:
            self._last_scroll_y = y
            self._scrolling = True
            return
        delta = self._last_scroll_y - y  # moving hand up -> positive -> scroll up, like a touchpad
        self._last_scroll_y = y
        if abs(delta) < self.config.scroll_deadzone:
            return
        ticks = int(delta * self.config.scroll_sensitivity)
        if ticks != 0:
            self.actions.scroll(ticks)
            self._set_action("scroll", now)
        self._scrolling = True

    def _set_action(self, name: str, now: float) -> None:
        self.status.last_action = name
        self.status.last_action_at = now
