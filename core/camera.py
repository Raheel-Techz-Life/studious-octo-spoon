"""Webcam capture: open, read frames, release, and report errors clearly."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class FrameResult:
    ok: bool
    frame_bgr: np.ndarray | None = None
    error: str | None = None


class Camera:
    def __init__(self, device_index: int = 0, width: int = 640, height: int = 480):
        self.device_index = device_index
        self.width = width
        self.height = height
        self._cap: cv2.VideoCapture | None = None

    def open(self) -> FrameResult:
        self._cap = cv2.VideoCapture(self.device_index, cv2.CAP_DSHOW)
        if not self._cap.isOpened():
            # Retry without the DirectShow backend hint in case it's unsupported.
            self._cap = cv2.VideoCapture(self.device_index)
        if not self._cap.isOpened():
            self._cap = None
            return FrameResult(ok=False, error=(
                "Could not access the webcam. Check that it is connected, not in use "
                "by another application, and that camera permission is granted."
            ))
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        return FrameResult(ok=True)

    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    def read(self) -> FrameResult:
        if not self.is_open():
            return FrameResult(ok=False, error="Camera is not open.")
        ok, frame = self._cap.read()
        if not ok or frame is None:
            return FrameResult(ok=False, error="Failed to read a frame from the camera.")
        return FrameResult(ok=True, frame_bgr=frame)

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
