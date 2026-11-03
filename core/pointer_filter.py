"""Smoothing for the spatial pointer.

Raw fingertip coordinates from MediaPipe are noisy frame-to-frame; moving
the OS cursor directly from them is jittery and unusable. We use simple
exponential smoothing (a one-line, well-understood low-pass filter) rather
than a full One Euro filter: it has one tunable parameter (alpha), is cheap
enough to run every frame, and in testing removed visible jitter without
adding noticeable lag at the stability duration this project uses elsewhere.
A One Euro filter would adapt its cutoff to movement speed and could reduce
lag further on fast swipes; left as a documented future improvement rather
than added speculatively.
"""

from __future__ import annotations


def remap_to_region(x: float, y: float, x0: float, y0: float, x1: float, y1: float) -> tuple[float, float]:
    """Maps a point from the full camera frame (0-1) into a normalized 0-1
    position relative to a smaller "active region" of that frame, clamped
    at the edges. A smaller region means less hand travel is needed to
    cover the full mapped range (mouse screen, keyboard layout, launcher
    grid) - useful since a comfortably held hand rarely visits the camera
    frame's extreme edges.
    """
    w = max(1e-6, x1 - x0)
    h = max(1e-6, y1 - y0)
    nx = min(1.0, max(0.0, (x - x0) / w))
    ny = min(1.0, max(0.0, (y - y0) / h))
    return nx, ny


class ExponentialSmoother:
    """y[t] = alpha * x[t] + (1 - alpha) * y[t-1]. Higher alpha = less lag,
    more jitter. Lower alpha = smoother, more lag.
    """

    def __init__(self, alpha: float = 0.4):
        self.alpha = alpha
        self._value: tuple[float, float] | None = None

    def update(self, x: float, y: float) -> tuple[float, float]:
        if self._value is None:
            self._value = (x, y)
        else:
            px, py = self._value
            a = self.alpha
            self._value = (a * x + (1 - a) * px, a * y + (1 - a) * py)
        return self._value

    def reset(self) -> None:
        self._value = None
