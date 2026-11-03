"""Draws Face+Hand mode's effects: the finger-heart pulse (reuses
Expressive mode's renderer directly, since it's driven by the same
ExpressiveStatus shape) plus small floating hearts that drift upward and
fade after a confirmed "blow a kiss" sequence.
"""

from __future__ import annotations

import cv2
import numpy as np

from core.face_hand_interaction import FaceHandStatus
from ui.expressive_overlay import HEART_COLOR, draw_expressive_overlay, heart_points


def draw_face_hand_overlay(frame_rgb: np.ndarray, status: FaceHandStatus) -> np.ndarray:
    out = frame_rgb
    if status.finger_heart_status is not None:
        out = draw_expressive_overlay(out, status.finger_heart_status)
    if status.floating_hearts:
        out = _draw_floating_hearts(out, status)
    return out


def _draw_floating_hearts(frame_rgb: np.ndarray, status: FaceHandStatus) -> np.ndarray:
    h, w = frame_rgb.shape[:2]
    overlay = frame_rgb.copy()
    alpha = max(0.0, 1.0 - status.kiss_effect_progress)
    base_scale = min(h, w) * 0.05

    for heart in status.floating_hearts:
        cx, cy = int(heart.x * w), int(heart.y * h)
        if not (0 <= cx < w and -base_scale <= cy < h + base_scale):
            continue
        pts = heart_points(cx, cy, base_scale * heart.scale, steps=24)
        heart_layer = overlay.copy()
        cv2.fillPoly(heart_layer, [pts], HEART_COLOR, cv2.LINE_AA)
        cv2.addWeighted(heart_layer, alpha, overlay, 1 - alpha, 0, overlay)

    return overlay
