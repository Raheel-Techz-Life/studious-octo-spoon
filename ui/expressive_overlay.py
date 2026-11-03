"""Draws expressive-sign effects onto the camera frame with OpenCV: small
rotated rectangles for confetti/celebration, and a pulsing heart outline
for the I-Love-You sign. Same split as Magic Mode's overlay - this module
only reads an ExpressiveStatus snapshot and draws; no state, no timing.
"""

from __future__ import annotations

import math

import cv2
import numpy as np

from core.expressive_signs import ExpressiveStatus

HEART_COLOR = (255, 90, 140)


def draw_expressive_overlay(frame_rgb: np.ndarray, status: ExpressiveStatus) -> np.ndarray:
    if status.effect_progress >= 1.0:
        return frame_rgb

    h, w = frame_rgb.shape[:2]
    overlay = frame_rgb.copy()

    if status.active_action == "heart":
        _draw_pulsing_heart(overlay, w, h, status.effect_progress)
    elif status.particles:
        for p in status.particles:
            px, py = int(p.x * w), int(p.y * h)
            if not (0 <= px < w and 0 <= py < h):
                continue
            _draw_confetti_piece(overlay, px, py, p.rotation_deg, p.color)

    return overlay


def _draw_confetti_piece(frame: np.ndarray, cx: int, cy: int, rotation_deg: float,
                          color: tuple[int, int, int]) -> None:
    size = 6
    angle = math.radians(rotation_deg)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    corners = []
    for dx, dy in ((-size, -size // 2), (size, -size // 2), (size, size // 2), (-size, size // 2)):
        rx = dx * cos_a - dy * sin_a
        ry = dx * sin_a + dy * cos_a
        corners.append([int(cx + rx), int(cy + ry)])
    pts = np.array(corners, dtype=np.int32)
    cv2.fillConvexPoly(frame, pts, color, cv2.LINE_AA)


def heart_points(cx: int, cy: int, scale: float, steps: int = 40) -> np.ndarray:
    """A parametric heart-curve outline centered at (cx, cy), `scale` pixels
    "radius". Shared by Expressive mode's pulsing heart and Face+Hand mode's
    floating hearts so the curve math lives in exactly one place."""
    points = []
    for i in range(steps + 1):
        t = (i / steps) * 2 * math.pi
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
        points.append([int(cx + x * scale / 16), int(cy + y * scale / 16)])
    return np.array(points, dtype=np.int32)


def _draw_pulsing_heart(frame: np.ndarray, w: int, h: int, progress: float) -> None:
    # A quick pulse: grows for the first third, settles back for the rest -
    # simple and readable rather than a physically "accurate" spring.
    pulse = math.sin(min(1.0, progress * 3) * math.pi / 2) if progress < 0.33 else \
        1.0 - (progress - 0.33) / 0.67 * 0.3
    scale = min(h, w) * 0.12 * max(0.0, pulse)
    cx, cy = w // 2, int(h * 0.4)

    pts = heart_points(cx, cy, scale)
    alpha = max(0.0, 1.0 - progress)
    heart_layer = frame.copy()
    cv2.fillPoly(heart_layer, [pts], HEART_COLOR, cv2.LINE_AA)
    cv2.addWeighted(heart_layer, alpha, frame, 1 - alpha, 0, frame)
    cv2.polylines(frame, [pts], isClosed=True, color=HEART_COLOR, thickness=2, lineType=cv2.LINE_AA)
