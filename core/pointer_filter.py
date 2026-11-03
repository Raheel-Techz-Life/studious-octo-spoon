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
