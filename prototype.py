"""Phase 1 smoke test: smallest possible webcam gesture-recognition loop.

Run: python prototype.py
Press 'q' to quit. Prints the recognized gesture + confidence to the console
and overlays it on an OpenCV preview window. No Streamlit, no stabilization -
this just proves the camera + MediaPipe pipeline works on this machine.
"""

import sys
import time

import cv2

from core.camera import Camera
from core.recognizer import GestureRecognizer


def main() -> int:
    print("Downloading/loading gesture recognition model (first run may take a moment)...")
    try:
        recognizer = GestureRecognizer(num_hands=1)
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL: could not initialize recognizer: {exc}")
        return 1

    camera = Camera(device_index=0)
    result = camera.open()
    if not result.ok:
        print(f"FATAL: {result.error}")
        return 1

    print("Camera open. Show a hand gesture. Press 'q' in the preview window to quit.")
    frame_count = 0
    start = time.monotonic()

    try:
        while True:
            frame_result = camera.read()
            if not frame_result.ok:
                print(f"WARNING: {frame_result.error}")
                continue

            frame_bgr = frame_result.frame_bgr
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            rec = recognizer.recognize(frame_rgb)

            frame_count += 1
            if rec.error:
                label = f"ERROR: {rec.error}"
            elif rec.gesture:
                label = f"{rec.gesture} ({rec.confidence:.2f})"
            else:
                label = "No gesture / no hand"

            cv2.putText(frame_bgr, label, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                        (0, 255, 0), 2)
            cv2.imshow("GestureBridge Prototype", frame_bgr)

            if frame_count % 30 == 0:
                elapsed = time.monotonic() - start
                print(f"[{elapsed:5.1f}s] frame {frame_count}: {label} | "
                      f"fps={frame_count / elapsed:.1f}")

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        camera.release()
        recognizer.close()
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    sys.exit(main())
