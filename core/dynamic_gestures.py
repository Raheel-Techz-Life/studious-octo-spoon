"""Dynamic (motion-based) gesture detection: swipes and circular movement,
analyzed from a rolling trajectory buffer rather than a single frame's hand
pose. This is what makes it different from the static GestureRecognizer
classifier used in Navigation mode - a swipe or circle only exists across
multiple frames, so detection needs to look at a short window of recent
positions and reason about the path's shape, not just "where is the hand
right now."

Tracks the wrist position (a stabler reference point for broad arm/hand
motion than the fingertip, which moves a lot during a swipe's natural hand
rotation) across a rolling time window, then applies two independent
geometric checks:

- Swipe: net displacement over the window must be large, the path must be
  reasonably straight (net displacement / total path length close to 1 -
  this rejects wobbly, back-and-forth motion that happens to end up far
  from where it started), the path's direction must not turn by more than
  a small cumulative angle (straightness alone isn't enough: a short arc
  of a circle is also nearly straight by that ratio, so this catches the
  difference between "slightly curved swipe" and "part of a circle"), and
  it must complete within a time budget (this rejects slow drift, e.g.
  someone just resting their hand to one side).
- Circle: fits a center point to the recent trajectory, checks the radius
  is large enough to be deliberate, and sums the *signed* angular change
  frame-to-frame to measure how much of a full rotation was actually
  traced (this is the "trajectory/geometric method" the project brief
  asks for, rather than checking whether the hand happened to visit a
  scattered set of positions that aren't actually arranged in a circle).

Both share one cooldown and one trajectory buffer: a detected event clears
the buffer so the same motion's tail end can't immediately re-trigger
another detection, and the buffer resets entirely if the hand disappears
mid-motion (an interrupted gesture must not fire as a completed one).
"""

from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable

from core import hand_landmarks as hl

SWIPE_LEFT = "swipe_left"
SWIPE_RIGHT = "swipe_right"
SWIPE_UP = "swipe_up"
SWIPE_DOWN = "swipe_down"
CIRCLE_CLOCKWISE = "circle_clockwise"
CIRCLE_COUNTERCLOCKWISE = "circle_counterclockwise"


@dataclass
class DynamicGestureConfig:
    buffer_duration_s: float = 1.2       # how much trajectory history is kept at most
    swipe_min_distance: float = 0.22     # normalized net displacement required
    swipe_max_duration_s: float = 0.6    # must complete within this window (rejects slow drift)
    swipe_min_straightness: float = 0.75  # net displacement / path length; 1.0 = perfectly straight
    swipe_max_cumulative_turn_deg: float = 45.0  # rejects paths that curve too much to be a straight swipe
    circle_min_radius: float = 0.07
    circle_min_coverage_deg: float = 300.0  # how much of a full rotation must be traced
    circle_max_duration_s: float = 2.0
    cooldown_s: float = 1.0


@dataclass
class DynamicGestureEvent:
    name: str
    at: float
    detail: dict = field(default_factory=dict)


class DynamicGestureDetector:
    def __init__(self, config: DynamicGestureConfig | None = None,
                 clock: Callable[[], float] = time.monotonic):
        self.config = config or DynamicGestureConfig()
        self._clock = clock
        self._points: deque[tuple[float, float, float]] = deque()  # (t, x, y)
        self._last_event_time: float | None = None
        self.last_event: DynamicGestureEvent | None = None

    def reset(self) -> None:
        self._points.clear()

    def update(self, landmarks: list[tuple[float, float]] | None) -> DynamicGestureEvent | None:
        now = self._clock()
        if not landmarks:
            # An interrupted motion must not be evaluated as if it completed.
            self.reset()
            return None

        x, y = landmarks[hl.WRIST]
        self._points.append((now, x, y))
        cutoff = now - self.config.buffer_duration_s
        while self._points and self._points[0][0] < cutoff:
            self._points.popleft()

        if self._last_event_time is not None and now - self._last_event_time < self.config.cooldown_s:
            return None

        event = self._detect_swipe(now) or self._detect_circle(now)
        if event is not None:
            self._last_event_time = now
            self.last_event = event
            self._points.clear()  # a fresh gesture must start from a clean trajectory
        return event

    def _recent(self, now: float, max_age_s: float) -> list[tuple[float, float, float]]:
        start_t = now - max_age_s
        return [p for p in self._points if p[0] >= start_t]

    def _detect_swipe(self, now: float) -> DynamicGestureEvent | None:
        pts = self._recent(now, self.config.swipe_max_duration_s)
        if len(pts) < 4:
            return None
        t0, x0, y0 = pts[0]
        t1, x1, y1 = pts[-1]
        dx, dy = x1 - x0, y1 - y0
        net_dist = math.hypot(dx, dy)
        if net_dist < self.config.swipe_min_distance:
            return None

        path_len = sum(
            math.hypot(pts[i][1] - pts[i - 1][1], pts[i][2] - pts[i - 1][2])
            for i in range(1, len(pts))
        )
        if path_len <= 1e-9:
            return None
        straightness = net_dist / path_len
        if straightness < self.config.swipe_min_straightness:
            return None  # too wobbly to be a deliberate swipe

        cumulative_turn_deg = self._cumulative_turn_degrees(pts)
        if cumulative_turn_deg > self.config.swipe_max_cumulative_turn_deg:
            return None  # a short arc of a circle can also score "straight" by the ratio above

        if abs(dx) >= abs(dy):
            name = SWIPE_RIGHT if dx > 0 else SWIPE_LEFT
        else:
            name = SWIPE_DOWN if dy > 0 else SWIPE_UP
        return DynamicGestureEvent(name, now, {
            "distance": net_dist, "duration_s": t1 - t0, "straightness": straightness,
        })

    @staticmethod
    def _cumulative_turn_degrees(pts: list[tuple[float, float, float]]) -> float:
        """Sum of absolute direction-change angles between consecutive
        movement segments - near 0 for a straight line, growing quickly
        for any curved or circular path."""
        if len(pts) < 3:
            return 0.0
        total = 0.0
        prev_angle = None
        for i in range(1, len(pts)):
            dx = pts[i][1] - pts[i - 1][1]
            dy = pts[i][2] - pts[i - 1][2]
            if dx == 0 and dy == 0:
                continue
            angle = math.atan2(dy, dx)
            if prev_angle is not None:
                d = angle - prev_angle
                while d > math.pi:
                    d -= 2 * math.pi
                while d < -math.pi:
                    d += 2 * math.pi
                total += abs(d)
            prev_angle = angle
        return math.degrees(total)

    def _detect_circle(self, now: float) -> DynamicGestureEvent | None:
        pts = self._recent(now, self.config.circle_max_duration_s)
        if len(pts) < 8:
            return None

        xs = [p[1] for p in pts]
        ys = [p[2] for p in pts]
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        radii = [math.hypot(x - cx, y - cy) for x, y in zip(xs, ys)]
        avg_r = sum(radii) / len(radii)
        if avg_r < self.config.circle_min_radius:
            return None
        # Reject a wildly inconsistent radius (e.g. a swipe that happens to
        # curve a little) - a real circle keeps a roughly constant radius.
        radius_spread = (max(radii) - min(radii)) / avg_r
        if radius_spread > 1.0:
            return None

        angles = [math.atan2(y - cy, x - cx) for x, y in zip(xs, ys)]
        total_delta = 0.0
        for i in range(1, len(angles)):
            d = angles[i] - angles[i - 1]
            while d > math.pi:
                d -= 2 * math.pi
            while d < -math.pi:
                d += 2 * math.pi
            total_delta += d
        coverage_deg = abs(math.degrees(total_delta))
        if coverage_deg < self.config.circle_min_coverage_deg:
            return None

        name = CIRCLE_CLOCKWISE if total_delta < 0 else CIRCLE_COUNTERCLOCKWISE
        return DynamicGestureEvent(name, now, {
            "coverage_deg": coverage_deg, "avg_radius": avg_r,
        })
