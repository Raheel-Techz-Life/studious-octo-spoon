"""Draws Magic Mode's visual effect directly onto the camera frame with
OpenCV - chosen as the "lightweight rendering" the project brief asks for
(no 3D engine, no browser canvas/JS layer to keep in sync with the video).
Original, generic fantasy visuals (a rotating ring, small rune-like marks,
an outward particle burst) - nothing copied from any specific film.

Pure rendering: reads a MagicStatus snapshot (see core/magic_effects.py)
and returns a new frame. No state, no timing logic, so it's trivial to
reason about and doesn't need the state machine's own unit tests repeated
here - only that it runs without error and returns a same-shaped frame.
"""

from __future__ import annotations

import math

import cv2
import numpy as np

from core.magic_effects import MagicStatus

RING_COLOR = (255, 170, 60)      # amber glow, RGB (frame is RGB throughout this app)
RUNE_COLOR = (255, 210, 140)
PARTICLE_COLOR = (255, 200, 80)
BURST_RING_COLOR = (255, 140, 40)


def draw_magic_overlay(frame_rgb: np.ndarray, status: MagicStatus) -> np.ndarray:
    if not status.tracking or status.hand_pos is None:
        return frame_rgb

    h, w = frame_rgb.shape[:2]
    px = int(status.hand_pos[0] * w)
    py = int(status.hand_pos[1] * h)
    base_radius = int(min(w, h) * (0.07 + 0.05 * status.intensity))

    overlay = frame_rgb.copy()

    # Soft glow: a couple of faint, blended filled circles under everything else.
    for radius_mult, alpha in ((1.3, 0.12), (1.1, 0.22)):
        glow_layer = overlay.copy()
        cv2.circle(glow_layer, (px, py), int(base_radius * radius_mult), RING_COLOR, -1, cv2.LINE_AA)
        cv2.addWeighted(glow_layer, alpha, overlay, 1 - alpha, 0, overlay)

    # Idle ring: a dashed circle that rotates continuously.
    phase = math.radians(status.idle_phase_deg)
    dash_count = 16
    for i in range(dash_count):
        if i % 2 == 0:
            continue
        a0 = phase + 2 * math.pi * i / dash_count
        a1 = a0 + (2 * math.pi / dash_count) * 0.6
        p0 = (int(px + base_radius * math.cos(a0)), int(py + base_radius * math.sin(a0)))
        p1 = (int(px + base_radius * math.cos(a1)), int(py + base_radius * math.sin(a1)))
        cv2.line(overlay, p0, p1, RING_COLOR, 2, cv2.LINE_AA)

    # Rune marks: small triangles on a wider ring, rotating the other way.
    rune_radius = base_radius * 1.6
    rune_phase = math.radians(-status.idle_phase_deg * 1.5)
    for i in range(6):
        a = rune_phase + 2 * math.pi * i / 6
        rx = int(px + rune_radius * math.cos(a))
        ry = int(py + rune_radius * math.sin(a))
        size = 6
        pts = np.array([[rx, ry - size], [rx - size, ry + size], [rx + size, ry + size]], dtype=np.int32)
        cv2.polylines(overlay, [pts], isClosed=True, color=RUNE_COLOR, thickness=1, lineType=cv2.LINE_AA)

    # Burst: an expanding, fading ring plus outward-moving particles.
    if status.bursting and status.burst_center is not None:
        bpx = int(status.burst_center[0] * w)
        bpy = int(status.burst_center[1] * h)
        expand_radius = int(base_radius * (1 + 3 * status.burst_progress))
        fade_alpha = max(0.0, 1.0 - status.burst_progress)

        burst_layer = overlay.copy()
        cv2.circle(burst_layer, (bpx, bpy), max(1, expand_radius), BURST_RING_COLOR, 3, cv2.LINE_AA)
        cv2.addWeighted(burst_layer, fade_alpha, overlay, 1 - fade_alpha, 0, overlay)

        particle_radius = max(1, int(3 * fade_alpha) + 1)
        for p in status.particles:
            ppx, ppy = int(p.x * w), int(p.y * h)
            if 0 <= ppx < w and 0 <= ppy < h:
                cv2.circle(overlay, (ppx, ppy), particle_radius, PARTICLE_COLOR, -1, cv2.LINE_AA)

    return overlay
