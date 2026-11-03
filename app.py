"""GestureBridge: webcam hand-gesture control, built on Streamlit.

Architecture note on Streamlit's rerun model: Streamlit reruns the whole
script on every widget interaction, which would normally mean re-opening the
camera and resetting all state on every click. We avoid that by:
  - Keeping the camera, recognizer, controller, stabilizer, and logger as
    long-lived objects in st.session_state, created once on "Start camera".
  - Driving the live camera loop with an st.fragment(run_every=...), which
    reruns ONLY that fragment, not the whole page, so sidebar widgets and
    their state are untouched while the feed updates ~10x/sec.
"""

from __future__ import annotations

import time

import cv2
import streamlit as st

from core.camera import Camera
from core.event_logger import EventLogger
from core.gesture_controller import COMMANDS, DEFAULT_MAPPING, GestureController
from core.stabilization import GestureStabilizer, StabilizationConfig
from ui import components
from ui.styles import CSS
from utils.audio_feedback import AudioFeedback
from utils.metrics import events_to_dataframe, summarize

try:
    from core.recognizer import MEDIAPIPE_AVAILABLE, GestureRecognizer
except Exception:
    MEDIAPIPE_AVAILABLE = False

DEMO_CARDS = [
    "Welcome to GestureBridge",
    "Card 2 — hands-free navigation demo",
    "Card 3 — show a Thumbs Up to confirm",
    "Card 4 — this is the last card",
]

st.set_page_config(page_title="GestureBridge", page_icon="🖐️", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)


def init_state() -> None:
    defaults = {
        "running": False,
        "paused": False,
        "demo_index": 0,
        "confirmed": False,
        "stability_s": 0.5,
        "cooldown_s": 1.0,
        "min_confidence": 0.6,
        "audio_on": False,
        "camera_error": None,
        "engine_error": None,
        "last_status_text": "No hand detected",
        "last_confidence": 0.0,
        "mapping": dict(DEFAULT_MAPPING),
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    if "event_logger" not in st.session_state:
        st.session_state.event_logger = EventLogger(max_events=200)
    if "controller" not in st.session_state:
        st.session_state.controller = GestureController(
            st.session_state.event_logger, mapping=st.session_state.mapping
        )
    if "audio" not in st.session_state:
        st.session_state.audio = AudioFeedback()


def register_demo_handlers() -> None:
    controller: GestureController = st.session_state.controller

    def do_next():
        st.session_state.demo_index = min(len(DEMO_CARDS) - 1, st.session_state.demo_index + 1)

    def do_back():
        st.session_state.demo_index = max(0, st.session_state.demo_index - 1)

    def do_confirm():
        st.session_state.confirmed = True

    def do_reset():
        st.session_state.demo_index = 0
        st.session_state.confirmed = False

    controller.register_handler("next", do_next)
    controller.register_handler("back", do_back)
    controller.register_handler("confirm", do_confirm)
    controller.register_handler("reset", do_reset)
    # "pause" is handled specially in the fragment loop (it toggles the
    # controller's own enabled flag, so it must work even while disabled).


def start_camera() -> None:
    if st.session_state.running:
        return  # already running; avoid leaking a second camera/recognizer handle

    if not MEDIAPIPE_AVAILABLE:
        st.session_state.engine_error = (
            "mediapipe is not installed in this environment. Install it with: "
            "pip install mediapipe"
        )
        return

    camera = Camera(device_index=0)
    result = camera.open()
    if not result.ok:
        st.session_state.camera_error = result.error
        return

    try:
        recognizer = GestureRecognizer(num_hands=1)
    except Exception as exc:  # noqa: BLE001
        camera.release()
        st.session_state.engine_error = f"Could not load the gesture model: {exc}"
        return

    st.session_state.camera = camera
    st.session_state.recognizer = recognizer
    st.session_state.stabilizer = GestureStabilizer(StabilizationConfig(
        stability_duration_s=st.session_state.stability_s,
        cooldown_s=st.session_state.cooldown_s,
        min_confidence=st.session_state.min_confidence,
    ))
    st.session_state.camera_error = None
    st.session_state.engine_error = None
    st.session_state.running = True


def stop_camera() -> None:
    camera: Camera | None = st.session_state.get("camera")
    recognizer = st.session_state.get("recognizer")
    if camera is not None:
        camera.release()
    if recognizer is not None:
        recognizer.close()
    st.session_state.camera = None
    st.session_state.recognizer = None
    st.session_state.running = False
    st.session_state.last_status_text = "Camera stopped"


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown("### Controls")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("▶ Start camera", disabled=st.session_state.running,
                         use_container_width=True):
                start_camera()
                st.rerun()  # refresh header/button state immediately, not on the next fragment tick
        with col2:
            if st.button("■ Stop camera", disabled=not st.session_state.running,
                         use_container_width=True):
                stop_camera()
                st.rerun()

        st.session_state.controller.enabled = st.toggle(
            "Command execution enabled", value=st.session_state.controller.enabled,
            help="Pause this to stop gestures from triggering commands, "
                 "without stopping the camera.",
        )

        st.markdown("#### Sensitivity")
        st.session_state.min_confidence = st.slider(
            "Minimum confidence", 0.1, 0.95, st.session_state.min_confidence, 0.05)
        st.session_state.stability_s = st.slider(
            "Stability duration (s)", 0.1, 2.0, st.session_state.stability_s, 0.1,
            help="How long a gesture must hold steady before it triggers a command.")
        st.session_state.cooldown_s = st.slider(
            "Cooldown (s)", 0.2, 3.0, st.session_state.cooldown_s, 0.1,
            help="Minimum gap before the same gesture can trigger again.")

        if "stabilizer" in st.session_state and st.session_state.stabilizer is not None:
            st.session_state.stabilizer.config.min_confidence = st.session_state.min_confidence
            st.session_state.stabilizer.config.stability_duration_s = st.session_state.stability_s
            st.session_state.stabilizer.config.cooldown_s = st.session_state.cooldown_s

        st.session_state.audio_on = st.toggle(
            "Audio feedback", value=st.session_state.audio_on,
            disabled=not st.session_state.audio.available,
            help="Spoken confirmation when a command executes." if st.session_state.audio.available
            else "No local text-to-speech engine detected on this machine.",
        )

        if st.button("Reset session", use_container_width=True):
            st.session_state.event_logger.clear()
            st.session_state.demo_index = 0
            st.session_state.confirmed = False
            if "stabilizer" in st.session_state and st.session_state.stabilizer is not None:
                st.session_state.stabilizer.reset()

        st.markdown("---")
        st.markdown("#### Gesture mapping")
        for gesture, command in st.session_state.mapping.items():
            components.mapping_row(gesture, command)


@st.fragment(run_every=0.15)
def live_fragment() -> None:
    camera: Camera | None = st.session_state.get("camera")
    recognizer = st.session_state.get("recognizer")
    stabilizer: GestureStabilizer | None = st.session_state.get("stabilizer")
    controller: GestureController = st.session_state.controller

    frame_placeholder = st.empty()
    status_col1, status_col2, status_col3 = st.columns(3)

    if not st.session_state.running or camera is None or recognizer is None:
        frame_placeholder.info(
            "Camera is stopped. Click **Start camera** in the sidebar to begin, "
            "or use the manual demo mode below if no webcam is available."
        )
    else:
        frame_result = camera.read()
        if not frame_result.ok:
            st.session_state.last_status_text = f"Camera error: {frame_result.error}"
        else:
            frame_bgr = frame_result.frame_bgr
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            rec = recognizer.recognize(frame_rgb)

            if rec.error:
                st.session_state.last_status_text = f"Recognition error: {rec.error}"
            elif rec.gesture is None:
                st.session_state.last_status_text = "No hand detected"
                st.session_state.last_confidence = 0.0
            else:
                st.session_state.last_status_text = rec.gesture.replace("_", " ")
                st.session_state.last_confidence = rec.confidence

            fire, stab_state, latency_ms = stabilizer.update(
                rec.gesture if not rec.error else None, rec.confidence if not rec.error else 0.0
            )

            if fire == "Open_Palm":
                controller.enabled = not controller.enabled
                st.session_state.event_logger.record(
                    fire, "pause" if not controller.enabled else "resume", status="executed",
                    latency_ms=latency_ms,
                )
            elif fire is not None:
                result = controller.handle(fire, latency_ms=latency_ms)
                if result.status == "executed" and st.session_state.audio_on:
                    st.session_state.audio.speak(result.command or fire)

            frame_placeholder.image(frame_rgb, channels="RGB", use_container_width=True)

            with status_col1:
                components.stat("Recognized gesture", st.session_state.last_status_text)
            with status_col2:
                components.stat("Confidence", f"{st.session_state.last_confidence:.2f}")
            with status_col3:
                label = "Paused" if not controller.enabled else "Active"
                kind = "warn" if not controller.enabled else "ok"
                st.markdown(components.pill(label, kind), unsafe_allow_html=True)

            st.caption("Stabilization progress")
            components.progress_bar(stab_state.progress)
            if stab_state.in_cooldown:
                st.caption(f"Cooldown: {stab_state.cooldown_remaining_s:.1f}s remaining")

    render_demo_panel()
    render_history_and_analytics()


def render_demo_panel() -> None:
    components.card_open("In-app demo (what commands act on)")
    idx = st.session_state.demo_index
    st.markdown(f"**{DEMO_CARDS[idx]}**  \n_Card {idx + 1} of {len(DEMO_CARDS)}_")
    if st.session_state.confirmed:
        st.markdown(components.pill("Confirmed", "ok"), unsafe_allow_html=True)
    components.card_close()


def render_history_and_analytics() -> None:
    logger: EventLogger = st.session_state.event_logger
    events = logger.all()
    df = events_to_dataframe(events)
    summary = summarize(df)

    col_hist, col_stats = st.columns([3, 2])

    with col_hist:
        components.card_open("Event history")
        if df.empty:
            st.caption("No events yet. Perform a gesture to see it here.")
        else:
            st.dataframe(
                df[["timestamp", "gesture", "command", "status"]].head(20),
                use_container_width=True, hide_index=True,
            )
        components.card_close()

    with col_stats:
        components.card_open("Analytics")
        s1, s2 = st.columns(2)
        with s1:
            components.stat("Recognized", str(summary["total_recognized"]))
        with s2:
            components.stat("Executed", str(summary["total_executed"]))

        by_command = summary["by_command"]
        if not by_command.empty:
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=(4, 2.2))
            fig.patch.set_alpha(0)
            ax.set_facecolor("none")
            ax.bar(by_command.index, by_command.values, color="#5ee6a4")
            ax.tick_params(colors="#a8afc0")
            for spine in ax.spines.values():
                spine.set_color("#2b3040")
            ax.set_ylabel("count", color="#a8afc0")
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)

        latencies = [e.latency_ms for e in events if e.latency_ms is not None]
        if latencies:
            avg_latency = sum(latencies) / len(latencies)
            st.caption(f"Avg recognition-to-command latency: {avg_latency:.0f} ms "
                       f"(n={len(latencies)})")
        components.card_close()


def render_manual_fallback() -> None:
    with st.expander("Manual demo mode (no camera needed)"):
        st.caption(
            "If the webcam or gesture model is unavailable, trigger commands directly "
            "to demonstrate the rest of the system."
        )
        cols = st.columns(len(COMMANDS))
        controller: GestureController = st.session_state.controller
        gesture_by_command = {v: k for k, v in st.session_state.mapping.items()}
        for col, command in zip(cols, COMMANDS):
            with col:
                if st.button(command.capitalize(), use_container_width=True, key=f"manual_{command}"):
                    gesture = gesture_by_command.get(command, command)
                    if command == "pause":
                        # Pause must work even while execution is disabled (it's the
                        # on/off switch itself), so it bypasses the normal enabled-gate
                        # the same way the live camera path does for Open_Palm.
                        controller.enabled = not controller.enabled
                        st.session_state.event_logger.record(
                            gesture, "pause" if not controller.enabled else "resume",
                            status="executed",
                        )
                        st.rerun()  # refresh the sidebar toggle, which already rendered this pass
                    else:
                        controller.handle(gesture)


def main() -> None:
    init_state()
    register_demo_handlers()

    camera_status = "Running" if st.session_state.running else "Stopped"
    camera_kind = "ok" if st.session_state.running else "neutral"
    if st.session_state.camera_error:
        camera_status, camera_kind = "Error", "danger"

    if not MEDIAPIPE_AVAILABLE:
        engine_status, engine_kind = "Not installed", "danger"
    elif st.session_state.engine_error:
        engine_status, engine_kind = "Error", "danger"
    elif st.session_state.running:
        engine_status, engine_kind = "Loaded", "ok"
    else:
        engine_status, engine_kind = "Idle", "neutral"

    components.header(camera_status, camera_kind, engine_status, engine_kind)

    if st.session_state.camera_error:
        st.error(st.session_state.camera_error)
    if st.session_state.engine_error:
        st.error(st.session_state.engine_error)

    render_sidebar()
    live_fragment()
    render_manual_fallback()


if __name__ == "__main__":
    main()
