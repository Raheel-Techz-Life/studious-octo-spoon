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
from core.event_logger import EventLogger
from core.gesture_controller import GestureController
from core.launcher_controller import LauncherController, LauncherStatus
from core.mouse_controller import MouseController, MouseStatus
from core.recognizer import GestureRecognizer
from core.spatial_keyboard import KeyboardController, KeyboardStatus
from core.stabilization import GestureStabilizer, StabilizationState

MODES = ("navigation", "mouse", "keyboard", "launcher", "paused")


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
    fps: float = 0.0


class InteractionEngine:
    def __init__(self, controller: GestureController, event_logger: EventLogger,
                 nav_stabilizer: GestureStabilizer, mouse_controller: MouseController,
                 keyboard_controller: KeyboardController | None = None,
                 launcher_controller: LauncherController | None = None):
        self.controller = controller
        self.event_logger = event_logger
        self.nav_stabilizer = nav_stabilizer
        self.mouse_controller = mouse_controller
        self.keyboard_controller = keyboard_controller or KeyboardController()
        self.launcher_controller = launcher_controller or LauncherController()

        self.camera: Camera | None = None
        self.recognizer: GestureRecognizer | None = None
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

        while not self._stop_event.is_set():
            frame_result = self.camera.read()
            if not frame_result.ok:
                with self._snap_lock:
                    self._snapshot.error = frame_result.error
                continue

            frame_bgr = frame_result.frame_bgr
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            rec = self.recognizer.recognize(frame_rgb)

            mode = self.mode
            nav_stab_state = None
            mouse_status = None
            keyboard_status = None
            launcher_status = None

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
            # "paused": do nothing - frame is still captured/displayed, no actions fire

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
                    fps=fps,
                )
