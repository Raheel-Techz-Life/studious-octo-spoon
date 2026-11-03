"""Background tracking loop, decoupled from Streamlit's rerun cycle.

Why this exists: the original GestureBridge MVP read one camera frame per
Streamlit fragment tick (~every 150ms, ~6-7fps) - fine for discrete,
stabilized commands like "next slide", but far too slow for a smooth mouse
pointer, which needs to track the real camera frame rate (~30fps) to feel
responsive. Rather than forcing pointer updates through Streamlit's rerun
model, this engine owns the camera and recognizer itself and runs its own
loop in a background thread at full frame rate. Streamlit just polls
`get_snapshot()` on its own slower cadence to render the latest state -
the pointer itself moves at full speed regardless of how often Streamlit
redraws.

It reuses the existing camera/recognizer/stabilizer/controller/logger
exactly as the original Navigation mode used them; only the ownership moved
out of app.py and into this thread so Mouse mode could be added without
slowing Navigation mode down to the pointer's needs or speeding Navigation
up in a way that was never required.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

import cv2
import numpy as np

from core.camera import Camera
from core.dynamic_gestures import (
    CIRCLE_CLOCKWISE,
    CIRCLE_COUNTERCLOCKWISE,
    SWIPE_DOWN,
    SWIPE_LEFT,
    SWIPE_RIGHT,
    SWIPE_UP,
    DynamicGestureDetector,
    DynamicGestureEvent,
)
from core.event_logger import EventLogger
from core.expressive_signs import ExpressiveEngine, ExpressiveStatus
from core.face_hand_interaction import FaceHandEngine, FaceHandStatus
from core.face_recognizer import FaceRecognizer
from core.gesture_controller import GestureController
from core.launcher_controller import LauncherController, LauncherStatus
from core.magic_effects import MagicEffectState, MagicStatus
from core.mouse_controller import MouseController, MouseStatus
from core.recognizer import GestureRecognizer
from core.spatial_keyboard import KeyboardController, KeyboardStatus
from core.stabilization import GestureStabilizer, StabilizationState

MODES = ("navigation", "mouse", "keyboard", "launcher", "magic", "expressive", "face_hand", "paused")

# Dynamic (motion) gestures only act in Navigation mode, where they drive
# the same in-app demo commands static gestures do. Circular movement has
# no demo command mapped to it yet - it's only acknowledged/displayed for
# now (Magic Mode, a later roadmap priority, is the natural home for a real
# circle-triggered effect, and will reuse this same detector).
DYNAMIC_GESTURE_COMMANDS = {
    SWIPE_LEFT: "back",
    SWIPE_RIGHT: "next",
    SWIPE_UP: "confirm",
    SWIPE_DOWN: "reset",
}


@dataclass
class EngineSnapshot:
    tracking: bool = False
    mode: str = "navigation"
    frame_rgb: np.ndarray | None = None
    gesture: str | None = None
    confidence: float = 0.0
    error: str | None = None
    nav_stab_state: StabilizationState | None = None
    mouse_status: MouseStatus | None = None
    keyboard_status: KeyboardStatus | None = None
    launcher_status: LauncherStatus | None = None
    magic_status: MagicStatus | None = None
    expressive_status: ExpressiveStatus | None = None
    face_hand_status: FaceHandStatus | None = None
    last_dynamic_gesture: DynamicGestureEvent | None = None
    fps: float = 0.0


class InteractionEngine:
    def __init__(self, controller: GestureController, event_logger: EventLogger,
                 nav_stabilizer: GestureStabilizer, mouse_controller: MouseController,
                 keyboard_controller: KeyboardController | None = None,
                 launcher_controller: LauncherController | None = None,
                 magic_state: MagicEffectState | None = None,
                 expressive_engine: ExpressiveEngine | None = None,
                 face_hand_engine: FaceHandEngine | None = None):
        self.controller = controller
        self.event_logger = event_logger
        self.nav_stabilizer = nav_stabilizer
        self.mouse_controller = mouse_controller
        self.keyboard_controller = keyboard_controller or KeyboardController()
        self.launcher_controller = launcher_controller or LauncherController()
        self.magic_state = magic_state or MagicEffectState()
        self.expressive_engine = expressive_engine or ExpressiveEngine()
        self.face_hand_engine = face_hand_engine or FaceHandEngine()
        self.dynamic_detector = DynamicGestureDetector()
        self.dynamic_gestures_enabled = True

        self.camera: Camera | None = None
        self.recognizer: GestureRecognizer | None = None
        # Only ever created/destroyed by _run(), the one thread that uses it -
        # see the "face_hand" branch below. This genuinely stops face
        # tracking (not just ignores its output) the moment the mode is left,
        # per the project brief's privacy requirements.
        self.face_recognizer: FaceRecognizer | None = None
        self.face_recognizer_error: str | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

        self._mode_lock = threading.Lock()
        self._mode = "navigation"

        self._snap_lock = threading.Lock()
        self._snapshot = EngineSnapshot()

        self.start_error: str | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def mode(self) -> str:
        with self._mode_lock:
            return self._mode

    def set_mode(self, mode: str) -> None:
        if mode not in MODES:
            raise ValueError(f"unknown mode: {mode}")
        with self._mode_lock:
            self._mode = mode
        # Switching modes mid-gesture must not carry a held pinch/drag or a
        # half-stabilized gesture into the new mode's interpretation of it.
        if mode != "mouse":
            self.mouse_controller.reset()
        if mode != "navigation":
            self.nav_stabilizer.reset()
        if mode != "keyboard":
            self.keyboard_controller.reset()
        if mode != "launcher":
            self.launcher_controller.reset()
        if mode != "navigation":
            self.dynamic_detector.reset()
        if mode != "magic":
            self.magic_state.reset()
        if mode != "expressive":
            self.expressive_engine.reset()
        if mode != "face_hand":
            self.face_hand_engine.reset()

    def start(self) -> bool:
        if self.running:
            return True

        camera = Camera(device_index=0)
        result = camera.open()
        if not result.ok:
            self.start_error = result.error
            return False

        try:
            recognizer = GestureRecognizer(num_hands=1)
        except Exception as exc:  # noqa: BLE001
            camera.release()
            self.start_error = f"Could not load the gesture model: {exc}"
            return False

        self.camera = camera
        self.recognizer = recognizer
        self.start_error = None
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._thread = None
        self.mouse_controller.reset()  # release a stuck button/drag if mid-gesture
        if self.camera is not None:
            self.camera.release()
            self.camera = None
        if self.recognizer is not None:
            self.recognizer.close()
            self.recognizer = None
        if self.face_recognizer is not None:
            self.face_recognizer.close()
            self.face_recognizer = None
        with self._snap_lock:
            self._snapshot = EngineSnapshot()

    def get_snapshot(self) -> EngineSnapshot:
        with self._snap_lock:
            s = self._snapshot
            # Shallow copy is enough: fields are replaced wholesale each
            # tick in _run, never mutated in place.
            return EngineSnapshot(**s.__dict__)

    def _run(self) -> None:
        frame_count = 0
        fps_window_start = time.monotonic()
        fps = 0.0
        first_failure_at: float | None = None

        while not self._stop_event.is_set():
            frame_result = self.camera.read()
            if not frame_result.ok:
                now = time.monotonic()
                if first_failure_at is None:
                    first_failure_at = now
                stalled_s = now - first_failure_at
                # A handful of failed reads right after opening is normal -
                # some Windows DirectShow drivers take a moment to start
                # streaming. But with no sleep here at all, this loop would
                # busy-spin a full CPU core, which can itself starve the
                # camera driver's own thread and keep it from ever producing
                # a frame - turning a transient warm-up delay into a
                # permanent hang. Back off, and after a real timeout surface
                # a clear, visible error instead of spinning silently
                # forever (which looked like "camera never opens").
                time.sleep(0.05)
                with self._snap_lock:
                    self._snapshot.tracking = True
                    if stalled_s > 5.0:
                        self._snapshot.error = (
                            f"{frame_result.error} (no frame in {stalled_s:.0f}s - "
                            "check Windows Settings > Privacy & security > Camera > "
                            "Let desktop apps access your camera, and that no other "
                            "app is using the webcam)"
                        )
                    else:
                        self._snapshot.error = frame_result.error
                continue
            first_failure_at = None

            frame_bgr = frame_result.frame_bgr
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            rec = self.recognizer.recognize(frame_rgb)

            mode = self.mode
            nav_stab_state = None
            mouse_status = None
            keyboard_status = None
            launcher_status = None
            magic_status = None
            expressive_status = None
            face_hand_status = None

            if mode == "navigation":
                gesture = rec.gesture if not rec.error else None
                confidence = rec.confidence if not rec.error else 0.0
                fire, nav_stab_state, latency_ms = self.nav_stabilizer.update(gesture, confidence)
                if fire == "Open_Palm":
                    self.controller.enabled = not self.controller.enabled
                    self.event_logger.record(
                        fire, "pause" if not self.controller.enabled else "resume",
                        status="executed", latency_ms=latency_ms,
                    )
                elif fire is not None:
                    self.controller.handle(fire, latency_ms=latency_ms)

                landmarks = rec.landmarks if not rec.error and rec.landmarks else None
                dyn_event = self.dynamic_detector.update(landmarks) if self.dynamic_gestures_enabled else None
                if dyn_event is not None:
                    command = DYNAMIC_GESTURE_COMMANDS.get(dyn_event.name)
                    if command is not None:
                        self.controller.invoke_command(dyn_event.name, command)
                    elif dyn_event.name in (CIRCLE_CLOCKWISE, CIRCLE_COUNTERCLOCKWISE):
                        # No demo command mapped yet; still logged so it's
                        # visible in the event history and analytics.
                        self.event_logger.record(dyn_event.name, "detected", status="executed")
            elif mode == "mouse" and self.mouse_controller is not None:
                # Mouse mode tracks the hand shape directly (pinch distance,
                # finger extension), not the discrete gesture classifier, so
                # it works as long as a hand - any hand pose - is visible.
                landmarks = rec.landmarks if not rec.error and rec.landmarks else None
                try:
                    mouse_status = self.mouse_controller.update(landmarks)
                except Exception as exc:  # noqa: BLE001
                    # pyautogui's fail-safe (cursor driven into a screen
                    # corner) raises here; without this guard the whole
                    # background thread would die silently and the pointer
                    # would freeze with no visible error. Reset state and
                    # keep the loop (and the rest of the app) alive.
                    self.mouse_controller.reset()
                    with self._snap_lock:
                        self._snapshot.error = f"Mouse control error: {exc}"
            elif mode == "keyboard":
                landmarks = rec.landmarks if not rec.error and rec.landmarks else None
                keyboard_status = self.keyboard_controller.update(landmarks)
            elif mode == "launcher":
                landmarks = rec.landmarks if not rec.error and rec.landmarks else None
                launcher_status = self.launcher_controller.update(landmarks)
            elif mode == "magic":
                landmarks = rec.landmarks if not rec.error and rec.landmarks else None
                magic_status = self.magic_state.update(landmarks)
            elif mode == "expressive":
                # Expressive signs key off the discrete gesture classifier
                # (like Navigation mode), not raw landmarks - a "sign" is a
                # static pose, not a hand shape to track continuously.
                gesture = rec.gesture if not rec.error else None
                confidence = rec.confidence if not rec.error else 0.0
                expressive_status = self.expressive_engine.update(gesture, confidence)
            elif mode == "face_hand":
                if self.face_recognizer is None and self.face_recognizer_error is None:
                    try:
                        self.face_recognizer = FaceRecognizer()
                    except Exception as exc:  # noqa: BLE001
                        self.face_recognizer_error = f"Could not load the face model: {exc}"
                if self.face_recognizer is not None:
                    face_rec = self.face_recognizer.recognize(frame_rgb)
                    hand_landmarks = rec.landmarks if not rec.error and rec.landmarks else None
                    face_landmarks = (face_rec.landmarks
                                       if not face_rec.error and face_rec.landmarks else None)
                    face_hand_status = self.face_hand_engine.update(hand_landmarks, face_landmarks)
                elif self.face_recognizer_error:
                    with self._snap_lock:
                        self._snapshot.error = self.face_recognizer_error
            # "paused": do nothing - frame is still captured/displayed, no actions fire

            # Face tracking only runs while face_hand mode is active - tear it
            # down the moment the mode is left, in this same thread that owns
            # it, rather than leaving it loaded "just in case" the mode is
            # revisited.
            if mode != "face_hand" and self.face_recognizer is not None:
                self.face_recognizer.close()
                self.face_recognizer = None
                self.face_recognizer_error = None

            frame_count += 1
            now = time.monotonic()
            if now - fps_window_start >= 1.0:
                fps = frame_count / (now - fps_window_start)
                frame_count = 0
                fps_window_start = now

            with self._snap_lock:
                self._snapshot = EngineSnapshot(
                    tracking=True,
                    mode=mode,
                    frame_rgb=frame_rgb,
                    gesture=rec.gesture if not rec.error else None,
                    confidence=rec.confidence if not rec.error else 0.0,
                    error=rec.error,
                    nav_stab_state=nav_stab_state,
                    mouse_status=mouse_status,
                    keyboard_status=keyboard_status,
                    launcher_status=launcher_status,
                    magic_status=magic_status,
                    expressive_status=expressive_status,
                    face_hand_status=face_hand_status,
                    last_dynamic_gesture=self.dynamic_detector.last_event,
                    fps=fps,
                )
