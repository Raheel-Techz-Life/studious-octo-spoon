"""Spatial keyboard: the index fingertip moves a selection cursor over a
virtual QWERTY layout, and a deliberate pinch (not a pass-over hover)
selects the highlighted key. Reuses the same pointer-smoothing approach as
the spatial mouse, but never touches the OS - it only writes into an
in-app text buffer (see README: system-wide typing is explicitly out of
scope for now).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from core import hand_landmarks as hl
from core.keyboard_layout import Key, KeyboardLayout
from core.pointer_filter import ExponentialSmoother, remap_to_region


@dataclass
class KeyboardConfig:
    smoothing_alpha: float = 0.4
    mirror_x: bool = True
    pinch_threshold: float = 0.45
    select_cooldown_s: float = 0.25  # minimum gap between two key selections, even on different keys
    # Active region: a sub-rectangle of the camera frame (normalized 0-1)
    # that maps to the full key layout. Defaults to the full frame (no
    # remapping) so a hand has to visit every edge to reach the outer
    # keys - the app configures a smaller, more forgiving region for live
    # use (see app.py), but the identity default keeps this controller's
    # own coordinate math simple and testable in isolation.
    region_x0: float = 0.0
    region_y0: float = 0.0
    region_x1: float = 1.0
    region_y1: float = 1.0


@dataclass
class KeyboardStatus:
    tracking: bool = False
    pointer_norm: tuple[float, float] | None = None
    highlighted_key: str | None = None
    pinching: bool = False
    last_selected_key: str | None = None
    last_selected_at: float = 0.0
    shift_active: bool = False
    caps_lock: bool = False
    text: str = ""


class KeyboardController:
    def __init__(self, layout: KeyboardLayout | None = None, config: KeyboardConfig | None = None):
        self.layout = layout or KeyboardLayout()
        self.config = config or KeyboardConfig()
        self._smoother = ExponentialSmoother(self.config.smoothing_alpha)
        self._pinched = False
        self._pinch_key_counts: dict[str, int] = {}
        self._last_select_time = 0.0
        self.status = KeyboardStatus()

    def set_smoothing(self, alpha: float) -> None:
        self.config.smoothing_alpha = alpha
        self._smoother.alpha = alpha

    def reset(self) -> None:
        text = self.status.text  # typed text survives a mode switch/hand loss
        shift = self.status.shift_active
        caps = self.status.caps_lock
        self._pinched = False
        self._pinch_key_counts = {}
        self._smoother.reset()
        self.status = KeyboardStatus(text=text, shift_active=shift, caps_lock=caps)

    def clear_text(self) -> None:
        self.status.text = ""

    def update(self, landmarks: list[tuple[float, float]] | None) -> KeyboardStatus:
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

        key = self.layout.key_at(smooth_x, smooth_y)
        self.status.highlighted_key = key.id if key else None

        pinch_dist = hl.distance(landmarks, hl.THUMB_TIP, hl.INDEX_TIP) / scale
        is_pinched = pinch_dist < self.config.pinch_threshold

        # A shaky hand tends to flick sideways right at the instant the
        # fingers come apart to release the pinch, which - if only that one
        # frame's position decided the key - made the wrong neighboring key
        # get selected. Instead, track every key seen under the fingertip
        # for the whole pinch hold and select whichever one it spent the
        # most frames over; a brief end-of-release jitter is then outvoted
        # by the frames spent actually resting on the intended key.
        if is_pinched and key is not None:
            self._pinch_key_counts[key.id] = self._pinch_key_counts.get(key.id, 0) + 1

        now = time.monotonic()
        if is_pinched and not self._pinched:
            self._pinched = True
        elif not is_pinched and self._pinched:
            self._pinched = False
            settled_id = max(self._pinch_key_counts, key=self._pinch_key_counts.get) \
                if self._pinch_key_counts else None
            settled_key = self.layout.get(settled_id) if settled_id else None
            self._pinch_key_counts = {}
            since_last = now - self._last_select_time
            if settled_key is not None and since_last >= self.config.select_cooldown_s:
                self._select(settled_key, now)

        self.status.pinching = self._pinched
        return self.status

    def _select(self, key: Key, now: float) -> None:
        if key.char is not None:
            ch = key.char.upper() if (self.status.shift_active or self.status.caps_lock) else key.char.lower()
            self.status.text += ch
            if self.status.shift_active:
                self.status.shift_active = False  # one-shot, like a real shift tap
        elif key.id == "SPACE":
            self.status.text += " "
        elif key.id == "BACKSPACE":
            self.status.text = self.status.text[:-1]
        elif key.id == "ENTER":
            self.status.text += "\n"
        elif key.id == "SHIFT":
            self.status.shift_active = not self.status.shift_active
        elif key.id == "CAPS":
            self.status.caps_lock = not self.status.caps_lock
        elif key.id == "CLEAR":
            self.status.text = ""

        self.status.last_selected_key = key.id
        self.status.last_selected_at = now
        self._last_select_time = now
