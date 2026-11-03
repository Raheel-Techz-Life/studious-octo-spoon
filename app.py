"""GestureBridge: webcam hand-gesture control, built on Streamlit.

Architecture note on Streamlit's rerun model: Streamlit reruns the whole
script on every widget interaction, which would normally mean re-opening the
camera and resetting all state on every click. We avoid that by keeping the
camera, recognizer, controller, stabilizer, and mouse controller as
long-lived objects in st.session_state, created once on "Start tracking".

Architecture note on real-time tracking: the actual camera/recognizer loop
now runs in a background thread (core/interaction_engine.py), independent of
Streamlit's rerun cadence. Navigation mode's discrete, stabilized gestures
never needed more than a few updates per second, but Mouse mode's pointer
does - tracking the real camera frame rate rather than Streamlit's render
cadence is what makes the cursor feel responsive instead of laggy. The
Streamlit fragment below just polls the engine's latest snapshot on its own
timer to render it; it does not drive the tracking loop itself.
"""

from __future__ import annotations

import time

import numpy as np
import streamlit as st

from core.event_logger import EventLogger
from core.gesture_controller import COMMANDS, DEFAULT_MAPPING, GestureController
from core.interaction_engine import InteractionEngine
from core.mouse_controller import MouseConfig, MouseController
from core.stabilization import GestureStabilizer, StabilizationConfig
from ui import components
from ui.styles import CSS
from utils.audio_feedback import AudioFeedback
from utils.metrics import events_to_dataframe, summarize

try:
    from core.recognizer import MEDIAPIPE_AVAILABLE
except Exception:
    MEDIAPIPE_AVAILABLE = False

DEMO_CARDS = [
    "Welcome to GestureBridge",
    "Card 2 — hands-free navigation demo",
    "Card 3 — show a Thumbs Up to confirm",
    "Card 4 — this is the last card",
]

MODE_LABELS = {"navigation": "Navigation (gestures)", "mouse": "Mouse (pointer control)", "paused": "Paused"}

st.set_page_config(page_title="GestureBridge", page_icon="🖐️", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)


def init_state() -> None:
    defaults = {
        "mode": "navigation",
        "demo_index": 0,
        "confirmed": False,
        "stability_s": 0.5,
        "cooldown_s": 1.0,
        "min_confidence": 0.6,
        "audio_on": False,
        "start_error": None,
        "mapping": dict(DEFAULT_MAPPING),
        # Mouse mode settings
        "mouse_sensitivity": 1.0,   # bigger = smaller active region = less hand travel needed
        "mouse_smoothing": 0.4,
        "mouse_mirror": True,
        "mouse_click_enabled": True,
        "mouse_right_click_enabled": True,
        "mouse_drag_enabled": True,
        "mouse_scroll_enabled": True,
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
    if "engine" not in st.session_state:
        nav_stabilizer = GestureStabilizer(StabilizationConfig(
            stability_duration_s=st.session_state.stability_s,
            cooldown_s=st.session_state.cooldown_s,
            min_confidence=st.session_state.min_confidence,
        ))
        mouse_controller = _build_mouse_controller()
        st.session_state.engine = InteractionEngine(
            controller=st.session_state.controller,
            event_logger=st.session_state.event_logger,
            nav_stabilizer=nav_stabilizer,
            mouse_controller=mouse_controller,
        )


def _build_mouse_controller() -> MouseController:
    margin = max(0.02, 0.35 / max(0.2, st.session_state.mouse_sensitivity))
    cfg = MouseConfig(
        smoothing_alpha=st.session_state.mouse_smoothing,
        mirror_x=st.session_state.mouse_mirror,
        region_x0=margin, region_y0=margin, region_x1=1 - margin, region_y1=1 - margin,
        click_enabled=st.session_state.mouse_click_enabled,
        right_click_enabled=st.session_state.mouse_right_click_enabled,
        drag_enabled=st.session_state.mouse_drag_enabled,
        scroll_enabled=st.session_state.mouse_scroll_enabled,
    )
    try:
        return MouseController(config=cfg)
    except Exception:
        # pyautogui can fail to import/initialize in a headless or
        # permission-restricted environment; Mouse mode degrades to
        # "unavailable" rather than crashing the whole app.
        return None


def _sync_mouse_config() -> None:
    engine: InteractionEngine = st.session_state.engine
    mc = engine.mouse_controller
    if mc is None:
        return
    margin = max(0.02, 0.35 / max(0.2, st.session_state.mouse_sensitivity))
    mc.set_smoothing(st.session_state.mouse_smoothing)
    mc.config.mirror_x = st.session_state.mouse_mirror
    mc.config.region_x0, mc.config.region_y0 = margin, margin
    mc.config.region_x1, mc.config.region_y1 = 1 - margin, 1 - margin
    mc.config.click_enabled = st.session_state.mouse_click_enabled
    mc.config.right_click_enabled = st.session_state.mouse_right_click_enabled
    mc.config.drag_enabled = st.session_state.mouse_drag_enabled
    mc.config.scroll_enabled = st.session_state.mouse_scroll_enabled


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
    # "pause" is handled specially (toggles the controller's own enabled
    # flag), both in the engine and in the manual fallback button below, so
    # it works even while execution is disabled.


def start_tracking() -> None:
    engine: InteractionEngine = st.session_state.engine
    if engine.start():
        st.session_state.start_error = None
    else:
        st.session_state.start_error = engine.start_error


def stop_tracking() -> None:
    st.session_state.engine.stop()


def set_mode(mode: str) -> None:
    st.session_state.mode = mode
    st.session_state.engine.set_mode(mode)


def render_sidebar() -> None:
    engine: InteractionEngine = st.session_state.engine
    with st.sidebar:
        st.markdown("### Tracking")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("▶ Start tracking", disabled=engine.running, use_container_width=True):
                start_tracking()
                st.rerun()
        with col2:
            if st.button("■ Stop tracking", disabled=not engine.running, use_container_width=True):
                stop_tracking()
                st.rerun()

        mode_keys = list(MODE_LABELS.keys())
        current_index = mode_keys.index(st.session_state.mode)
        chosen = st.radio("Mode", mode_keys, index=current_index,
                           format_func=lambda k: MODE_LABELS[k], key="mode_radio")
        if chosen != st.session_state.mode:
            set_mode(chosen)
            st.rerun()

        st.markdown("---")
        st.markdown("#### Navigation sensitivity")
        st.session_state.min_confidence = st.slider(
            "Minimum confidence", 0.1, 0.95, st.session_state.min_confidence, 0.05)
        st.session_state.stability_s = st.slider(
            "Stability duration (s)", 0.1, 2.0, st.session_state.stability_s, 0.1,
            help="How long a gesture must hold steady before it triggers a command.")
        st.session_state.cooldown_s = st.slider(
            "Cooldown (s)", 0.2, 3.0, st.session_state.cooldown_s, 0.1,
            help="Minimum gap before the same gesture can trigger again.")
        engine.nav_stabilizer.config.min_confidence = st.session_state.min_confidence
        engine.nav_stabilizer.config.stability_duration_s = st.session_state.stability_s
        engine.nav_stabilizer.config.cooldown_s = st.session_state.cooldown_s

        st.session_state.controller.enabled = st.toggle(
            "Navigation commands enabled", value=st.session_state.controller.enabled,
            help="Pause this to stop gestures from triggering navigation commands, "
                 "without stopping the camera.",
        )

        st.markdown("---")
        st.markdown("#### Mouse mode")
        if engine.mouse_controller is None:
            st.caption("Unavailable: pyautogui failed to initialize on this machine.")
        else:
            st.session_state.mouse_sensitivity = st.slider(
                "Pointer sensitivity", 0.3, 2.5, st.session_state.mouse_sensitivity, 0.1,
                help="Higher = less hand travel needed to cross the screen.")
            st.session_state.mouse_smoothing = st.slider(
                "Smoothing", 0.1, 1.0, st.session_state.mouse_smoothing, 0.05,
                help="Lower = smoother but laggier pointer. Higher = snappier but jittery.")
            st.session_state.mouse_mirror = st.toggle(
                "Mirror (move hand right -> pointer right)", value=st.session_state.mouse_mirror)
            c1, c2 = st.columns(2)
            with c1:
                st.session_state.mouse_click_enabled = st.toggle(
                    "Click (pinch)", value=st.session_state.mouse_click_enabled)
                st.session_state.mouse_drag_enabled = st.toggle(
                    "Drag (hold pinch)", value=st.session_state.mouse_drag_enabled)
            with c2:
                st.session_state.mouse_right_click_enabled = st.toggle(
                    "Right-click", value=st.session_state.mouse_right_click_enabled)
                st.session_state.mouse_scroll_enabled = st.toggle(
                    "Scroll (2-finger)", value=st.session_state.mouse_scroll_enabled)
            _sync_mouse_config()

        st.markdown("---")
        st.session_state.audio_on = st.toggle(
            "Audio feedback", value=st.session_state.audio_on,
            disabled=not st.session_state.audio.available,
            help="Spoken confirmation when a navigation command executes." if st.session_state.audio.available
            else "No local text-to-speech engine detected on this machine.",
        )

        if st.button("Reset session", use_container_width=True):
            st.session_state.event_logger.clear()
            st.session_state.demo_index = 0
            st.session_state.confirmed = False
            engine.nav_stabilizer.reset()
            if engine.mouse_controller is not None:
                engine.mouse_controller.reset()

        st.markdown("---")
        st.markdown("#### Gesture mapping (Navigation mode)")
        for gesture, command in st.session_state.mapping.items():
            components.mapping_row(gesture, command)


@st.fragment(run_every=0.15)
def live_fragment() -> None:
    engine: InteractionEngine = st.session_state.engine
    controller: GestureController = st.session_state.controller

    frame_placeholder = st.empty()
    status_col1, status_col2, status_col3 = st.columns(3)

    if not engine.running:
        frame_placeholder.info(
            "Tracking is stopped. Click **Start tracking** in the sidebar to begin, "
            "or use the manual demo mode below if no webcam is available."
        )
    else:
        snap = engine.get_snapshot()
        if snap.error:
            st.caption(f"Recognition error: {snap.error}")
        if snap.frame_rgb is not None:
            display_frame = snap.frame_rgb
            if snap.mode == "mouse" and snap.mouse_status and snap.mouse_status.pointer_norm:
                display_frame = _draw_pointer_overlay(snap.frame_rgb, snap.mouse_status)
            frame_placeholder.image(display_frame, channels="RGB", use_container_width=True)

        if snap.mode == "navigation":
            with status_col1:
                label = snap.gesture.replace("_", " ") if snap.gesture else "No hand detected"
                components.stat("Recognized gesture", label)
            with status_col2:
                components.stat("Confidence", f"{snap.confidence:.2f}")
            with status_col3:
                label = "Paused" if not controller.enabled else "Active"
                kind = "warn" if not controller.enabled else "ok"
                st.markdown(components.pill(label, kind), unsafe_allow_html=True)
            if snap.nav_stab_state is not None:
                st.caption("Stabilization progress")
                components.progress_bar(snap.nav_stab_state.progress)
                if snap.nav_stab_state.in_cooldown:
                    st.caption(f"Cooldown: {snap.nav_stab_state.cooldown_remaining_s:.1f}s remaining")

        elif snap.mode == "mouse":
            ms = snap.mouse_status
            with status_col1:
                components.stat("Hand tracking", "Yes" if ms and ms.tracking else "No")
            with status_col2:
                components.stat("State", (ms.state if ms else "idle").capitalize())
            with status_col3:
                recent = ms and ms.last_action and (time.monotonic() - ms.last_action_at) < 0.6
                if recent:
                    st.markdown(components.pill(ms.last_action.replace("_", " ").title(), "ok"),
                                unsafe_allow_html=True)
            st.caption(f"Engine FPS: {snap.fps:.0f}")

        elif snap.mode == "paused":
            st.info("Tracking is paused. No commands or pointer actions will fire.")

    render_demo_panel()
    render_history_and_analytics()


def _draw_pointer_overlay(frame_rgb: np.ndarray, mouse_status) -> np.ndarray:
    import cv2
    h, w = frame_rgb.shape[:2]
    nx, ny = mouse_status.pointer_norm
    # Overlay is drawn in camera-frame space using the same mirroring the
    # controller applied, so the dot tracks the fingertip the user sees.
    px, py = int(nx * w), int(ny * h)
    out = frame_rgb.copy()
    color = (255, 80, 80) if mouse_status.state in ("pinched", "dragging") else (80, 230, 160)
    cv2.circle(out, (px, py), 12, color, 3)
    cv2.circle(out, (px, py), 2, color, -1)
    return out


def render_demo_panel() -> None:
    components.card_open("In-app demo (what Navigation-mode commands act on)")
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
            "If the webcam or gesture model is unavailable, trigger Navigation-mode "
            "commands directly to demonstrate the rest of the system."
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
    engine: InteractionEngine = st.session_state.engine

    camera_status = "Running" if engine.running else "Stopped"
    camera_kind = "ok" if engine.running else "neutral"
    if st.session_state.start_error:
        camera_status, camera_kind = "Error", "danger"

    if not MEDIAPIPE_AVAILABLE:
        engine_status, engine_kind = "Not installed", "danger"
    elif st.session_state.start_error:
        engine_status, engine_kind = "Error", "danger"
    elif engine.running:
        engine_status, engine_kind = f"Loaded ({MODE_LABELS[st.session_state.mode]})", "ok"
    else:
        engine_status, engine_kind = "Idle", "neutral"

    components.header(camera_status, camera_kind, engine_status, engine_kind)

    if st.session_state.start_error:
        st.error(st.session_state.start_error)

    render_sidebar()
    live_fragment()
    render_manual_fallback()


if __name__ == "__main__":
    main()
