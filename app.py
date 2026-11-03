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

from core.app_launcher import AppRegistry
from core.demo_state import DemoState
from core.event_logger import EventLogger
from core.expressive_signs import ExpressiveEngine, ExpressiveSignRegistry
from core.face_hand_interaction import FaceHandEngine
from core.gesture_controller import COMMANDS, DEFAULT_MAPPING, GestureController
from core.interaction_engine import InteractionEngine
from core.launcher_controller import LauncherConfig, LauncherController
from core.magic_effects import MagicConfig, MagicEffectState
from core.mouse_controller import MouseConfig, MouseController
from core.spatial_keyboard import KeyboardConfig, KeyboardController
from core.stabilization import GestureStabilizer, StabilizationConfig
from ui import components
from ui.expressive_overlay import draw_expressive_overlay
from ui.face_hand_overlay import draw_face_hand_overlay
from ui.magic_overlay import draw_magic_overlay
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

MODE_LABELS = {
    "navigation": "Navigation (gestures)",
    "mouse": "Mouse (pointer control)",
    "keyboard": "Keyboard (spatial typing)",
    "launcher": "Launcher (open apps)",
    "magic": "Magic (circle for effects)",
    "expressive": "Expressive (celebrate signs)",
    "face_hand": "Face+Hand (finger heart / kiss)",
    "paused": "Paused",
}

MOUSE_LEGEND = [
    ("Move index finger", "Move the pointer"),
    ("Pinch thumb + index, release", "Click"),
    ("Pinch twice quickly, same spot", "Double-click"),
    ("Pinch thumb + middle finger", "Right-click"),
    ("Pinch, hold ~0.35s, then move", "Drag (release to drop)"),
    ("Index + middle up, move vertically", "Scroll"),
]

KEYBOARD_LEGEND = [
    ("Move index finger over a key", "Highlight it"),
    ("Pinch while over a key, release", "Type that key"),
    ("Pinch over Shift", "Capitalize next letter only"),
    ("Pinch over Caps", "Caps lock (toggle)"),
    ("Pinch over <-  /  Space / Enter", "Backspace / space / newline"),
    ("Pinch over Clear", "Erase all typed text"),
]

NAVIGATION_LEGEND = [
    ("Open Palm", "Pause / resume commands"),
    ("Thumb Up", "Confirm"),
    ("Victory sign", "Next"),
    ("Closed Fist", "Back"),
    ("I-Love-You sign", "Reset"),
    ("Swipe left / right / up / down", "Back / Next / Confirm / Reset"),
    ("Trace a full circle", "Detected (shown, no action yet)"),
]

LAUNCHER_LEGEND = [
    ("Move index finger over a tile", "Highlight it"),
    ("Pinch while over a tile, release", "Launch that app"),
]

MAGIC_LEGEND = [
    ("Show your hand", "Idle glow follows it"),
    ("Move your hand faster", "Glow brightens / grows"),
    ("Trace a full circle", "Particle burst"),
]

EXPRESSIVE_LEGEND = [
    ("Hold Thumbs Up", "Celebration confetti"),
    ("Hold Victory", "Confetti burst"),
    ("Hold I-Love-You sign", "Pulsing heart"),
]

FACE_HAND_LEGEND = [
    ("Thumb+index pinch, other 3 fingers curled", "Finger-heart pulse"),
    ("Same pinch, held near your mouth", "Floating hearts"),
]

st.set_page_config(page_title="GestureBridge", page_icon="🖐️", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)


def init_state() -> None:
    defaults = {
        "mode": "navigation",
        "stability_s": 0.5,
        "cooldown_s": 1.0,
        "min_confidence": 0.6,
        "audio_on": False,
        "start_error": None,
        "mapping": dict(DEFAULT_MAPPING),
        "dynamic_gestures_enabled": True,
        # Mouse mode settings
        "mouse_sensitivity": 1.0,   # bigger = smaller active region = less hand travel needed
        "mouse_smoothing": 0.4,
        "mouse_mirror": True,
        "mouse_click_enabled": True,
        "mouse_right_click_enabled": True,
        "mouse_drag_enabled": True,
        "mouse_scroll_enabled": True,
        # Keyboard mode settings
        "keyboard_smoothing": 0.4,
        "keyboard_mirror": True,
        # Launcher mode settings
        "launcher_smoothing": 0.4,
        "launcher_mirror": True,
        # Magic mode settings
        "magic_rotation_speed": 70.0,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    if "demo_state" not in st.session_state:
        st.session_state.demo_state = DemoState(card_count=len(DEMO_CARDS))

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
        keyboard_controller = KeyboardController(config=KeyboardConfig(
            smoothing_alpha=st.session_state.keyboard_smoothing,
            mirror_x=st.session_state.keyboard_mirror,
            region_x0=ACTIVE_REGION_MARGIN, region_y0=ACTIVE_REGION_MARGIN,
            region_x1=1 - ACTIVE_REGION_MARGIN, region_y1=1 - ACTIVE_REGION_MARGIN,
        ))
        launcher_controller = LauncherController(AppRegistry(), config=LauncherConfig(
            smoothing_alpha=st.session_state.launcher_smoothing,
            mirror_x=st.session_state.launcher_mirror,
            region_x0=ACTIVE_REGION_MARGIN, region_y0=ACTIVE_REGION_MARGIN,
            region_x1=1 - ACTIVE_REGION_MARGIN, region_y1=1 - ACTIVE_REGION_MARGIN,
        ))
        magic_state = MagicEffectState(MagicConfig())
        expressive_engine = ExpressiveEngine(ExpressiveSignRegistry())
        face_hand_engine = FaceHandEngine()
        st.session_state.engine = InteractionEngine(
            controller=st.session_state.controller,
            event_logger=st.session_state.event_logger,
            nav_stabilizer=nav_stabilizer,
            mouse_controller=mouse_controller,
            keyboard_controller=keyboard_controller,
            launcher_controller=launcher_controller,
            magic_state=magic_state,
            expressive_engine=expressive_engine,
            face_hand_engine=face_hand_engine,
        )


# How much of the camera frame's edge is trimmed off the "active region"
# that maps to the full mouse screen / keyboard layout / launcher grid. A
# hand held at a natural, comfortable distance rarely reaches the frame's
# actual edges, so without this margin the pointer (or key/app cursor)
# spends most of its time pinned against one side - previously reported as
# the pointer/cursor "sitting at the base" and missing intended targets.
ACTIVE_REGION_MARGIN = 0.12


def _build_mouse_controller() -> MouseController:
    margin = max(0.02, 0.15 / max(0.2, st.session_state.mouse_sensitivity))
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
    margin = max(0.02, 0.15 / max(0.2, st.session_state.mouse_sensitivity))
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
    demo_state: DemoState = st.session_state.demo_state

    controller.register_handler("next", demo_state.next)
    controller.register_handler("back", demo_state.back)
    controller.register_handler("confirm", demo_state.confirm)
    controller.register_handler("reset", demo_state.reset)
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
        st.session_state.dynamic_gestures_enabled = st.toggle(
            "Dynamic gestures (swipe / circle)", value=st.session_state.dynamic_gestures_enabled,
            help="Swipe left/right/up/down drives Back/Next/Confirm/Reset; a full "
                 "circular motion is detected and shown but not yet mapped to an action.",
        )
        engine.dynamic_gestures_enabled = st.session_state.dynamic_gestures_enabled

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
        st.markdown("#### Keyboard mode")
        kb: KeyboardController = engine.keyboard_controller
        st.session_state.keyboard_smoothing = st.slider(
            "Keyboard pointer smoothing", 0.1, 1.0, st.session_state.keyboard_smoothing, 0.05)
        st.session_state.keyboard_mirror = st.toggle(
            "Keyboard mirror", value=st.session_state.keyboard_mirror)
        kb.set_smoothing(st.session_state.keyboard_smoothing)
        kb.config.mirror_x = st.session_state.keyboard_mirror
        if st.button("Clear typed text", use_container_width=True):
            kb.clear_text()

        st.markdown("---")
        st.markdown("#### Launcher mode")
        launcher: LauncherController = engine.launcher_controller
        st.session_state.launcher_smoothing = st.slider(
            "Launcher pointer smoothing", 0.1, 1.0, st.session_state.launcher_smoothing, 0.05)
        st.session_state.launcher_mirror = st.toggle(
            "Launcher mirror", value=st.session_state.launcher_mirror)
        launcher.set_smoothing(st.session_state.launcher_smoothing)
        launcher.config.mirror_x = st.session_state.launcher_mirror
        with st.expander("Add a custom app"):
            new_name = st.text_input("Display name", key="new_app_name")
            new_target = st.text_input(
                "Target (exe name on PATH, or an absolute path)", key="new_app_target",
                help="Windows: e.g. 'code.exe' or 'C:\\Path\\To\\App.exe'. macOS: the .app name, e.g. 'Safari'.")
            if st.button("Add app", use_container_width=True, key="add_app_btn"):
                if new_name and new_target:
                    launcher.registry.add_custom(new_name, new_target)
                    st.rerun()
                else:
                    st.warning("Enter both a name and a target first.")
            visible = launcher.registry.visible_entries()
            custom = [e for e in visible if e.id.startswith("custom_")]
            if custom:
                st.caption("Custom apps:")
                for entry in custom:
                    c1, c2 = st.columns([4, 1])
                    with c1:
                        avail = "✓" if entry.is_available() else "unavailable"
                        st.caption(f"{entry.icon} {entry.name} ({avail})")
                    with c2:
                        if st.button("✕", key=f"remove_{entry.id}"):
                            launcher.registry.remove(entry.id)
                            st.rerun()

        st.markdown("---")
        st.markdown("#### Magic mode")
        st.caption(
            "Trace a full circle with your hand to trigger a burst. Switching "
            "to this mode is the deliberate activation step; switch away to exit."
        )
        magic: MagicEffectState = engine.magic_state
        st.session_state.magic_rotation_speed = st.slider(
            "Idle ring rotation speed (deg/s)", 20.0, 180.0, st.session_state.magic_rotation_speed, 10.0)
        magic.config.idle_rotation_speed_deg_s = st.session_state.magic_rotation_speed

        st.markdown("---")
        st.markdown("#### Expressive mode")
        st.caption(
            "Hold a registered sign steady to trigger its effect. Separate "
            "from Navigation mode, so the same gesture can mean something "
            "different here without conflict."
        )
        expressive: ExpressiveEngine = engine.expressive_engine
        for sign in expressive.registry.signs:
            enabled = st.checkbox(
                f"{sign.icon} {sign.display_name} → {sign.action}",
                value=sign.enabled, key=f"sign_enabled_{sign.id}",
            )
            if enabled != sign.enabled:
                expressive.registry.set_enabled(sign.id, enabled)
                st.rerun()

        st.markdown("---")
        st.markdown("#### Face+Hand mode")
        st.caption(
            "Make a finger-heart (thumb+index pinched, other fingers curled) "
            "for a heart pulse. Hold that same pinch near your mouth briefly "
            "for floating hearts - proximity to your mouth alone never "
            "triggers anything by itself, only together with the pinch. "
            "Face tracking only runs while this mode is active, and stops "
            "the moment you switch away."
        )

        st.markdown("---")
        st.session_state.audio_on = st.toggle(
            "Audio feedback", value=st.session_state.audio_on,
            disabled=not st.session_state.audio.available,
            help="Spoken confirmation when a navigation command executes." if st.session_state.audio.available
            else "No local text-to-speech engine detected on this machine.",
        )

        if st.button("Reset session", use_container_width=True):
            st.session_state.event_logger.clear()
            st.session_state.demo_state.reset()
            engine.nav_stabilizer.reset()
            if engine.mouse_controller is not None:
                engine.mouse_controller.reset()
            engine.keyboard_controller.reset()
            engine.keyboard_controller.clear_text()
            engine.launcher_controller.reset()
            engine.dynamic_detector.reset()
            engine.magic_state.reset()
            engine.expressive_engine.reset()
            engine.face_hand_engine.reset()

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
            st.warning(f"Camera/recognition issue: {snap.error}")
        if snap.frame_rgb is None:
            frame_placeholder.info("Starting camera... this can take a few seconds.")
        if snap.frame_rgb is not None:
            display_frame = snap.frame_rgb
            if snap.mode == "mouse" and snap.mouse_status and snap.mouse_status.pointer_norm:
                active = snap.mouse_status.state in ("pinched", "dragging")
                display_frame = _draw_pointer_overlay(snap.frame_rgb, snap.mouse_status.pointer_norm, active)
            elif snap.mode == "keyboard" and snap.keyboard_status and snap.keyboard_status.pointer_norm:
                display_frame = _draw_pointer_overlay(
                    snap.frame_rgb, snap.keyboard_status.pointer_norm, snap.keyboard_status.pinching)
            elif snap.mode == "launcher" and snap.launcher_status and snap.launcher_status.pointer_norm:
                display_frame = _draw_pointer_overlay(
                    snap.frame_rgb, snap.launcher_status.pointer_norm, snap.launcher_status.pinching)
            elif snap.mode == "magic" and snap.magic_status:
                display_frame = draw_magic_overlay(snap.frame_rgb, snap.magic_status)
            elif snap.mode == "expressive" and snap.expressive_status:
                display_frame = draw_expressive_overlay(snap.frame_rgb, snap.expressive_status)
            elif snap.mode == "face_hand" and snap.face_hand_status:
                display_frame = draw_face_hand_overlay(snap.frame_rgb, snap.face_hand_status)
            display_frame = _downscale_for_display(display_frame)
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
            dyn = snap.last_dynamic_gesture
            if dyn is not None and (time.monotonic() - dyn.at) < 1.2:
                st.markdown(
                    components.pill(f"Dynamic: {dyn.name.replace('_', ' ').title()}", "ok"),
                    unsafe_allow_html=True,
                )
            components.action_legend(NAVIGATION_LEGEND, "Navigation mode actions")

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
            components.action_legend(MOUSE_LEGEND, "Mouse mode actions")

        elif snap.mode == "keyboard":
            ks = snap.keyboard_status
            with status_col1:
                components.stat("Hand tracking", "Yes" if ks and ks.tracking else "No")
            with status_col2:
                mods = []
                if ks and ks.shift_active:
                    mods.append("Shift")
                if ks and ks.caps_lock:
                    mods.append("Caps")
                components.stat("Modifiers", ", ".join(mods) if mods else "None")
            with status_col3:
                recent = ks and ks.last_selected_key and (time.monotonic() - ks.last_selected_at) < 0.6
                if recent:
                    st.markdown(components.pill(ks.last_selected_key.replace("CHAR_", ""), "ok"),
                                unsafe_allow_html=True)
            components.action_legend(KEYBOARD_LEGEND, "Keyboard mode actions")
            if ks is not None:
                components.keyboard_panel(
                    engine.keyboard_controller.layout, ks.highlighted_key, ks.pinching,
                    ks.text, ks.shift_active, ks.caps_lock,
                )

        elif snap.mode == "launcher":
            ls = snap.launcher_status
            with status_col1:
                components.stat("Hand tracking", "Yes" if ls and ls.tracking else "No")
            with status_col2:
                highlighted_entry = None
                if ls and ls.highlighted_app_id:
                    highlighted_entry = engine.launcher_controller.registry.visible_entries()
                    highlighted_entry = next(
                        (e for e in highlighted_entry if e.id == ls.highlighted_app_id), None)
                components.stat("Highlighted", highlighted_entry.name if highlighted_entry else "None")
            with status_col3:
                recent = ls and ls.last_launched_name and (time.monotonic() - ls.last_launch_at) < 3.0
                if recent:
                    kind = "ok" if ls.last_launch_ok else "danger"
                    st.markdown(components.pill(ls.last_launched_name, kind), unsafe_allow_html=True)
            if ls and ls.last_launched_name and (time.monotonic() - ls.last_launch_at) < 3.0:
                st.caption(ls.last_launch_message or "")
            entries = engine.launcher_controller.registry.visible_entries()
            if not entries:
                st.caption("No apps configured for this platform. Add one in the sidebar.")
            else:
                components.launcher_panel(entries, ls.highlighted_app_id if ls else None,
                                           ls.pinching if ls else False)
            components.action_legend(LAUNCHER_LEGEND, "Launcher mode actions")

        elif snap.mode == "magic":
            ms = snap.magic_status
            with status_col1:
                components.stat("Hand tracking", "Yes" if ms and ms.tracking else "No")
            with status_col2:
                components.stat("Intensity", f"{ms.intensity:.2f}" if ms else "0.00")
            with status_col3:
                if ms and ms.bursting:
                    st.markdown(components.pill("Casting!", "ok"), unsafe_allow_html=True)
            if ms and not ms.tracking:
                st.caption("Show your hand to the camera, then trace a full circle to cast.")
            components.action_legend(MAGIC_LEGEND, "Magic mode actions")

        elif snap.mode == "expressive":
            es = snap.expressive_status
            with status_col1:
                label = es.gesture.replace("_", " ") if es and es.gesture else "No hand detected"
                components.stat("Recognized sign", label)
            with status_col2:
                components.stat("Confidence", f"{es.confidence:.2f}" if es else "0.00")
            with status_col3:
                recent = es and es.active_sign_id and es.effect_progress < 1.0
                if recent:
                    st.markdown(components.pill(f"{es.active_action}!", "ok"), unsafe_allow_html=True)
            if es is not None and es.stab_progress > 0.0:
                st.caption("Hold steady...")
                components.progress_bar(es.stab_progress)
            registry_list = ", ".join(
                f"{s.icon} {s.display_name}" for s in engine.expressive_engine.registry.signs if s.enabled
            )
            st.caption(f"Registered signs: {registry_list or 'none enabled'}")
            components.action_legend(EXPRESSIVE_LEGEND, "Expressive mode actions")

        elif snap.mode == "face_hand":
            fh = snap.face_hand_status
            with status_col1:
                components.stat("Hand tracking", "Yes" if fh and fh.hand_tracking else "No")
            with status_col2:
                components.stat("Face tracking", "Yes" if fh and fh.face_tracking else "No")
            with status_col3:
                fh_sign = fh.finger_heart_status if fh else None
                recent_heart = fh_sign and fh_sign.active_sign_id and fh_sign.effect_progress < 1.0
                recent_kiss = fh and fh.kiss_effect_progress < 1.0
                if recent_kiss:
                    st.markdown(components.pill("Kiss!", "ok"), unsafe_allow_html=True)
                elif recent_heart:
                    st.markdown(components.pill("Finger Heart!", "ok"), unsafe_allow_html=True)
            if fh is not None:
                if fh.near_mouth and fh.kiss_progress > 0.0:
                    st.caption("Hold near your mouth...")
                    components.progress_bar(fh.kiss_progress)
                elif not fh.face_tracking:
                    st.caption("Show your face to the camera for the kiss effect "
                               "(finger-heart works with just your hand).")
            components.action_legend(FACE_HAND_LEGEND, "Face+Hand mode actions")

        elif snap.mode == "paused":
            st.info("Tracking is paused. No commands or pointer actions will fire.")

    render_demo_panel()
    render_history_and_analytics()


def _draw_pointer_overlay(frame_rgb: np.ndarray, pointer_norm: tuple[float, float], active: bool) -> np.ndarray:
    import cv2
    h, w = frame_rgb.shape[:2]
    nx, ny = pointer_norm
    # Overlay is drawn in camera-frame space using the same mirroring the
    # controller applied, so the dot tracks the fingertip the user sees.
    px, py = int(nx * w), int(ny * h)
    out = frame_rgb.copy()
    color = (255, 80, 80) if active else (80, 230, 160)
    cv2.circle(out, (px, py), 12, color, 3)
    cv2.circle(out, (px, py), 2, color, -1)
    return out


_DISPLAY_MAX_WIDTH = 480  # downscaled before JPEG-encoding for display; recognition already ran on the full frame


def _downscale_for_display(frame_rgb: np.ndarray) -> np.ndarray:
    """Shrinks the frame before Streamlit JPEG-encodes it for display.
    Recognition/pointer mapping already happened on the full-resolution
    frame upstream of this call, so this only affects what's shown, not
    accuracy. JPEG-encoding a smaller image is the main lever here: it ran
    on every ~150ms UI tick and was real, measurable CPU work competing
    with the background tracking thread for the GIL."""
    import cv2
    h, w = frame_rgb.shape[:2]
    if w <= _DISPLAY_MAX_WIDTH:
        return frame_rgb
    scale = _DISPLAY_MAX_WIDTH / w
    new_size = (_DISPLAY_MAX_WIDTH, int(h * scale))
    return cv2.resize(frame_rgb, new_size, interpolation=cv2.INTER_AREA)


def render_demo_panel() -> None:
    components.card_open("In-app demo (what Navigation-mode commands act on)")
    idx = st.session_state.demo_state.index
    st.markdown(f"**{DEMO_CARDS[idx]}**  \n_Card {idx + 1} of {len(DEMO_CARDS)}_")
    if st.session_state.demo_state.confirmed:
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
            # Native st.bar_chart (Vega-Lite, rendered client-side) instead
            # of matplotlib: matplotlib was rebuilding and PNG-encoding a
            # whole figure from scratch on every ~150ms fragment tick, which
            # is real CPU work competing for the GIL with the background
            # tracking thread - a direct cause of the sluggishness noticed
            # in Mouse/Keyboard mode. This has no server-side render cost.
            st.bar_chart(by_command, color="#5ee6a4", height=180)

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
