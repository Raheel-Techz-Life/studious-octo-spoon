"""Loads MediaPipe's GestureRecognizer and normalizes results into a plain dataclass.

Uses the Tasks API (mediapipe.tasks.python.vision.GestureRecognizer) with the
pretrained gesture_recognizer.task bundle. See:
https://ai.google.dev/edge/mediapipe/solutions/vision/gesture_recognizer
"""

from __future__ import annotations

import os
import time
import urllib.request
from dataclasses import dataclass, field

import numpy as np

try:
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision
    MEDIAPIPE_AVAILABLE = True
except ImportError:
    MEDIAPIPE_AVAILABLE = False

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/"
    "gesture_recognizer/float16/1/gesture_recognizer.task"
)
MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")
MODEL_PATH = os.path.join(MODEL_DIR, "gesture_recognizer.task")

# Labels produced by the pretrained model (confirmed via its metadata).
# "None" means no gesture met the model's internal confidence threshold.
SUPPORTED_GESTURES = [
    "Open_Palm",
    "Closed_Fist",
    "Thumb_Up",
    "Thumb_Down",
    "Victory",
    "Pointing_Up",
    "ILoveYou",
]


@dataclass
class RecognitionResult:
    gesture: str | None  # e.g. "Thumb_Up", or None if no hand / no confident gesture
    confidence: float
    handedness: str | None
    landmarks: list[tuple[float, float]] = field(default_factory=list)
    timestamp_ms: int = 0
    error: str | None = None


def ensure_model_downloaded() -> str:
    """Downloads the pretrained model bundle on first run if not already present."""
    os.makedirs(MODEL_DIR, exist_ok=True)
    if not os.path.exists(MODEL_PATH):
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    return MODEL_PATH


class GestureRecognizer:
    """Thin wrapper around mediapipe's GestureRecognizer in VIDEO mode."""

    def __init__(self, model_path: str | None = None, num_hands: int = 1,
                 min_hand_detection_confidence: float = 0.5,
                 min_hand_presence_confidence: float = 0.5,
                 min_tracking_confidence: float = 0.5):
        if not MEDIAPIPE_AVAILABLE:
            raise RuntimeError(
                "mediapipe is not installed. Install it with: pip install mediapipe"
            )
        model_path = model_path or ensure_model_downloaded()
        base_options = mp_python.BaseOptions(model_asset_path=model_path)
        options = mp_vision.GestureRecognizerOptions(
            base_options=base_options,
            running_mode=mp_vision.RunningMode.VIDEO,
            num_hands=num_hands,
            min_hand_detection_confidence=min_hand_detection_confidence,
            min_hand_presence_confidence=min_hand_presence_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )
        self._recognizer = mp_vision.GestureRecognizer.create_from_options(options)
        self._start_time = time.monotonic()

    def recognize(self, frame_rgb: np.ndarray) -> RecognitionResult:
        """Runs inference on a single RGB frame (numpy array, HxWx3)."""
        timestamp_ms = int((time.monotonic() - self._start_time) * 1000)
        try:
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
            result = self._recognizer.recognize_for_video(mp_image, timestamp_ms)
        except Exception as exc:  # noqa: BLE001 - surface any inference failure to caller
            return RecognitionResult(
                gesture=None, confidence=0.0, handedness=None,
                timestamp_ms=timestamp_ms, error=str(exc),
            )

        if not result.gestures:
            return RecognitionResult(
                gesture=None, confidence=0.0, handedness=None, timestamp_ms=timestamp_ms,
            )

        top_gesture = result.gestures[0][0]
        handedness = result.handedness[0][0].category_name if result.handedness else None
        landmarks = []
        if result.hand_landmarks:
            landmarks = [(lm.x, lm.y) for lm in result.hand_landmarks[0]]

        gesture_name = top_gesture.category_name
        if gesture_name in ("", "None"):
            gesture_name = None

        return RecognitionResult(
            gesture=gesture_name,
            confidence=top_gesture.score,
            handedness=handedness,
            landmarks=landmarks,
            timestamp_ms=timestamp_ms,
        )

    def close(self) -> None:
        self._recognizer.close()
