"""Gesture-controlled application launcher: the index fingertip moves a
selection cursor over a grid of configured apps, and a deliberate
pinch-and-release confirms and launches the highlighted one.

Reuses the same pointer-smoothing and pinch-distance approach as Mouse and
Keyboard mode, but the "confirm" action calls a safe, explicit launch
function (core/app_launcher.py) instead of touching the OS pointer or a
text buffer.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from core import hand_landmarks as hl
from core.app_launcher import AppEntry, AppRegistry, launch as default_launch
from core.pointer_filter import ExponentialSmoother, remap_to_region


@dataclass
class LauncherConfig:
    smoothing_alpha: float = 0.4
    mirror_x: bool = True
    pinch_threshold: float = 0.45
    confirm_cooldown_s: float = 1.5  # avoid relaunching the same app repeatedly
    # Active region: see KeyboardConfig's region_* fields for why this
    # exists. Defaults to the full frame (identity mapping).
    region_x0: float = 0.0
    region_y0: float = 0.0
    region_x1: float = 1.0
    region_y1: float = 1.0


@dataclass
class LauncherStatus:
    tracking: bool = False
    pointer_norm: tuple[float, float] | None = None
    highlighted_app_id: str | None = None
    pinching: bool = False
    last_launched_name: str | None = None
    last_launch_ok: bool | None = None
    last_launch_message: str | None = None
    last_launch_at: float = 0.0


def grid_rects(count: int, columns: int = 4) -> list[tuple[float, float, float, float]]:
    """Normalized (x0, y0, x1, y1) rects for `count` tiles in a grid."""
    if count == 0:
        return []
    rows = (count + columns - 1) // columns
    rects = []
    for i in range(count):
        row, col = divmod(i, columns)
        cols_in_row = min(columns, count - row * columns)
        cell_w = 1.0 / cols_in_row
        cell_h = 1.0 / rows
        rects.append((col * cell_w, row * cell_h, (col + 1) * cell_w, (row + 1) * cell_h))
    return rects


class LauncherController:
    def __init__(self, registry: AppRegistry | None = None, config: LauncherConfig | None = None,
                 launch_fn: Callable[[AppEntry], tuple[bool, str]] | None = None):
        self.registry = registry or AppRegistry()
        self.config = config or LauncherConfig()
        self._launch_fn = launch_fn or default_launch
        self._smoother = ExponentialSmoother(self.config.smoothing_alpha)
        self._pinched = False
        self._last_launch_time = 0.0
        self.status = LauncherStatus()

    def set_smoothing(self, alpha: float) -> None:
        self.config.smoothing_alpha = alpha
        self._smoother.alpha = alpha

    def reset(self) -> None:
        last_name, last_ok, last_msg, last_at = (
            self.status.last_launched_name, self.status.last_launch_ok,
            self.status.last_launch_message, self.status.last_launch_at,
        )
        self._pinched = False
        self._smoother.reset()
        self.status = LauncherStatus(
            last_launched_name=last_name, last_launch_ok=last_ok,
            last_launch_message=last_msg, last_launch_at=last_at,
        )

    def _entry_at(self, x: float, y: float) -> AppEntry | None:
        entries = self.registry.visible_entries()
        rects = grid_rects(len(entries))
        for entry, (x0, y0, x1, y1) in zip(entries, rects):
            if x0 <= x < x1 and y0 <= y < y1:
                return entry
        return None

    def update(self, landmarks: list[tuple[float, float]] | None) -> LauncherStatus:
        if not landmarks:
            self.reset()
            return self.status

        self.status.tracking = True
        scale = hl.hand_scale(landmarks)
        if scale <= 1e-6:
            return self.status

        index_x, index_y = landmarks[hl.INDEX_TIP]
        if self.config.mirror_x:
            index_x = 1.0 - index_x
        cfg = self.config
        norm_x, norm_y = remap_to_region(
            index_x, index_y, cfg.region_x0, cfg.region_y0, cfg.region_x1, cfg.region_y1)
        smooth_x, smooth_y = self._smoother.update(norm_x, norm_y)
        self.status.pointer_norm = (smooth_x, smooth_y)

        entry = self._entry_at(smooth_x, smooth_y)
        self.status.highlighted_app_id = entry.id if entry else None

        pinch_dist = hl.distance(landmarks, hl.THUMB_TIP, hl.INDEX_TIP) / scale
        is_pinched = pinch_dist < self.config.pinch_threshold

        now = time.monotonic()
        if is_pinched and not self._pinched:
            self._pinched = True
        elif not is_pinched and self._pinched:
            self._pinched = False
            since_last = now - self._last_launch_time
            if entry is not None and since_last >= self.config.confirm_cooldown_s:
                self._confirm(entry, now)

        self.status.pinching = self._pinched
        return self.status

    def _confirm(self, entry: AppEntry, now: float) -> None:
        if not entry.is_available():
            self.status.last_launched_name = entry.name
            self.status.last_launch_ok = False
            self.status.last_launch_message = f"{entry.name} is not available on this system."
        else:
            ok, message = self._launch_fn(entry)
            self.status.last_launched_name = entry.name
            self.status.last_launch_ok = ok
            self.status.last_launch_message = message
        self.status.last_launch_at = now
        self._last_launch_time = now
