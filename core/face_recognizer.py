"""Loads MediaPipe's FaceLandmarker and normalizes results into a plain
dataclass - the face-tracking equivalent of core/recognizer.py.

Privacy, by construction, not just by policy:
- `output_face_blendshapes` is left False: this wrapper never requests or
  sees expression/blendshape data, so no code path here could be used for
  emotion inference even by accident.
- Only raw landmark *positions* are returned (a geometric point cloud),
  never an identity embedding - this model has no face-recognition output
  to begin with, so "not identifying the person" holds structurally.
- Nothing is written to disk by this module; frames and landmarks only
  ever live in memory for the current call.
- `InteractionEngine` only constructs this class when Face+Hand mode is
  active and closes it the moment the mode is left (see set_mode()) -
  tracking genuinely stops when the feature is disabled, not just ignored.

See https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker
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
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)
MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")
MODEL_PATH = os.path.join(MODEL_DIR, "face_landmarker.task")


@dataclass
class FaceRecognitionResult:
    landmarks: list[tuple[float, float]] = field(default_factory=list)  # empty if no face found
    error: str | None = None


def ensure_model_downloaded() -> str:
    os.makedirs(MODEL_DIR, exist_ok=True)
    if not os.path.exists(MODEL_PATH):
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    return MODEL_PATH


class FaceRecognizer:
    """Thin wrapper around mediapipe's FaceLandmarker in VIDEO mode. Only
    instantiate this while a face+hand feature is actually in use - see the
    module docstring."""

    def __init__(self, model_path: str | None = None,
                 min_face_detection_confidence: float = 0.5,
                 min_face_presence_confidence: float = 0.5,
                 min_tracking_confidence: float = 0.5):
        if not MEDIAPIPE_AVAILABLE:
            raise RuntimeError(
                "mediapipe is not installed. Install it with: pip install mediapipe"
            )
        model_path = model_path or ensure_model_downloaded()
        base_options = mp_python.BaseOptions(model_asset_path=model_path)
        options = mp_vision.FaceLandmarkerOptions(
            base_options=base_options,
            running_mode=mp_vision.RunningMode.VIDEO,
            num_faces=1,
            min_face_detection_confidence=min_face_detection_confidence,
            min_face_presence_confidence=min_face_presence_confidence,
            min_tracking_confidence=min_tracking_confidence,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=False,
        )
        self._landmarker = mp_vision.FaceLandmarker.create_from_options(options)
        self._start_time = time.monotonic()

    def recognize(self, frame_rgb: np.ndarray) -> FaceRecognitionResult:
        timestamp_ms = int((time.monotonic() - self._start_time) * 1000)
        try:
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
            result = self._landmarker.detect_for_video(mp_image, timestamp_ms)
        except Exception as exc:  # noqa: BLE001
            return FaceRecognitionResult(landmarks=[], error=str(exc))

        if not result.face_landmarks:
            return FaceRecognitionResult(landmarks=[])

        landmarks = [(lm.x, lm.y) for lm in result.face_landmarks[0]]
        return FaceRecognitionResult(landmarks=landmarks)

    def close(self) -> None:
        self._landmarker.close()
