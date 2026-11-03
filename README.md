# GestureBridge

> Your Hands. Your Commands. Your Freedom.

A webcam-based hand-gesture control prototype, started as a 24-hour hackathon
MVP and now being extended into a broader vision-based interaction platform.
Recognizes hand gestures and hand shape via MediaPipe and turns them into
either in-app navigation commands or real OS pointer control, with a
stabilization layer that prevents a single held gesture from firing
repeatedly.

**Status:** the Navigation-mode MVP (gesture → in-app command) and the
Mouse mode spatial pointer (Priority 1 of the advanced-features roadmap) are
implemented and tested. Keyboard, app launcher, dynamic gestures, Magic
Mode, expressive signs, and face+hand interaction are **not yet built** —
see the Progress checklist below for exactly what's done.

## Why

Traditional keyboard/mouse input can be a barrier for people with motor
impairments or temporary physical limitations. GestureBridge explores an
alternative: control a small set of actions with hand gestures in front of a
standard webcam, entirely locally — no cloud API, no footage upload.

This is a prototype demonstrating the interaction pattern, not a certified
assistive-technology product. Its accessibility benefits need real user
testing before any such claim is made.

## Setup

Requires Python 3.11–3.13 (MediaPipe's published wheels do not yet support
3.14+ at the time of writing — this project was built against **3.13**).

```bash
py -3.13 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Running

Phase 1 smoke test (plain OpenCV window, no Streamlit — proves the camera +
model pipeline works on your machine before touching the UI):

```bash
python prototype.py
```

Full application:

```bash
streamlit run app.py
```

Then, in the browser tab Streamlit opens, click **Start tracking** in the
sidebar, and pick a **Mode**: Navigation (the original gesture-command MVP),
Mouse (hand-controlled OS pointer), or Paused.

**Mouse mode moves your real OS cursor and can click.** `pyautogui`'s
fail-safe is left on (default): slam the cursor into any screen corner to
abort immediately. Nothing fires unless a hand is actually visible and
making the pinch/pose gestures described below — no hand in frame means no
OS actions at all.

## Running tests

```bash
pip install -r requirements-dev.txt
pytest
```

`tests/test_stabilization.py`, `tests/test_gesture_controller.py`, and
`tests/test_mouse_controller.py` cover the stabilization, command-mapping,
and pointer/click/drag/scroll state-machine logic directly (no camera,
model, or real OS mouse required — `test_mouse_controller.py` uses a fake
actions backend specifically so tests never move the real cursor).

## Architecture

```
gesturebridge/
├── app.py                      # Streamlit UI + wiring
├── prototype.py                 # Phase 1 standalone smoke test
├── core/
│   ├── camera.py                 # webcam open/read/release, error-safe
│   ├── recognizer.py             # MediaPipe GestureRecognizer wrapper
│   ├── hand_landmarks.py         # named landmark indices + geometry helpers
│   ├── gesture_controller.py     # gesture -> in-app command mapping + dispatch
│   ├── stabilization.py          # hold-to-confirm + cooldown logic (Navigation mode)
│   ├── mouse_controller.py       # pointer/click/double-click/right-click/drag/scroll state machine
│   ├── pointer_filter.py         # exponential smoothing for the cursor
│   ├── interaction_engine.py     # background tracking thread, owns camera+recognizer
│   └── event_logger.py           # bounded, thread-safe in-memory event history
├── ui/
│   ├── components.py              # Streamlit UI fragments
│   └── styles.py                   # dark, high-contrast theme CSS
├── utils/
│   ├── metrics.py                  # pandas aggregation for analytics
│   └── audio_feedback.py           # optional local TTS confirmation
└── tests/
    ├── test_stabilization.py
    ├── test_gesture_controller.py
    └── test_mouse_controller.py
```

**Data flow (Navigation mode):** `camera.py` grabs a frame → `recognizer.py`
runs MediaPipe inference and returns a plain `RecognitionResult` (gesture
label + real confidence score, never fabricated) → `stabilization.py` tracks
whether that gesture has held steady long enough, and enforces a cooldown →
only then does `gesture_controller.py` dispatch the mapped in-app command →
`event_logger.py` records what happened for the history/analytics panels.

**Data flow (Mouse mode):** same camera + recognizer, but `recognizer.py`'s
raw 21-point hand landmarks go to `mouse_controller.py` instead of the
discrete gesture classifier/stabilizer — it reads fingertip positions and
pinch distances directly every frame (via `hand_landmarks.py`'s geometry
helpers), smooths the index fingertip with `pointer_filter.py`, and turns
pinch/pose state transitions into real `pyautogui` pointer calls.

### Why there's now a background tracking thread

The original MVP read one camera frame per Streamlit fragment tick (every
150ms, ~6-7fps) - fine for discrete, stabilized Navigation commands, but far
too slow for a pointer to feel responsive. Rather than forcing Mouse mode's
high-frequency pointer updates through Streamlit's rerun model,
`interaction_engine.py` now owns the camera and recognizer itself and runs
its own loop in a daemon thread at the real camera frame rate. The Streamlit
fragment just polls `engine.get_snapshot()` on its own slower cadence to
render the latest state; the pointer itself moves at full speed regardless
of how often Streamlit redraws. `EventLogger` gained a lock because it's now
written from this background thread and read from Streamlit's render thread.

### Why Streamlit still needed care on top of that

Streamlit reruns the whole script on every widget interaction. This app
keeps the engine, controller, and mouse controller as long-lived objects in
`st.session_state` (created once), and the Start/Stop/Mode controls call
`st.rerun()` immediately after changing engine state — otherwise the header
status pills and button disabled-states, which render *before* the sidebar's
click handlers run in script order, would show stale values until some
unrelated later rerun happened to catch them up. This was an actual bug
found during manual testing (see Progress checklist), not a hypothetical.

## Supported gestures (pretrained model)

The bundled MediaPipe `gesture_recognizer.task` model supports these
categories: `Open_Palm`, `Closed_Fist`, `Thumb_Up`, `Thumb_Down`, `Victory`,
`Pointing_Up`, `ILoveYou` (plus `None` when no gesture meets its internal
threshold). Default mapping used by this app:

| Gesture | Command |
|---|---|
| Open Palm | Pause / resume command execution |
| Thumb Up | Confirm |
| Victory | Next |
| Closed Fist | Back |
| I Love You | Reset |

`Thumb_Down` and `Pointing_Up` are recognized by the model but left
unmapped in the default config — remap them in the sidebar if desired.

## Stabilization (the distinctive feature)

A command does not fire the instant a gesture is detected. Each frame's
prediction feeds `GestureStabilizer`, which:

1. Tracks how long the *same* gesture has been the top prediction.
2. Only allows a command to fire once that duration (default 0.5s,
   adjustable in the sidebar) is met.
3. Applies a cooldown (default 1.0s, adjustable) before the same gesture
   can fire again.
4. Resets immediately if the hand disappears or the prediction changes.

This is tested directly in `tests/test_stabilization.py` without needing a
camera.

## Mouse mode

Index fingertip controls the pointer; thumb-based pinches and a two-finger
pose control clicking:

| Gesture | Action |
|---|---|
| Move index finger | Move the pointer (smoothed, mapped from a configurable active region) |
| Pinch thumb + index, release | Click |
| Pinch thumb + index twice quickly in the same spot | Double-click |
| Pinch thumb + middle finger | Right-click |
| Pinch thumb + index, hold ~0.35s, then move | Drag (release pinch to drop) |
| Index + middle extended, ring + pinky curled, move vertically | Scroll |

All of click/right-click/drag/scroll can be individually disabled in the
sidebar. Sensitivity controls how large the "active region" of the camera
frame is (smaller region = less hand travel to cross the whole screen);
smoothing trades responsiveness for jitter reduction (simple exponential
smoothing — see `core/pointer_filter.py` for why that was chosen over a
full One Euro filter). Losing the hand, or switching away from Mouse mode,
immediately releases any held mouse button rather than leaving it stuck
down — covered by `test_hand_lost_mid_drag_releases_the_button` and
`InteractionEngine.set_mode()`.

`pyautogui`'s fail-safe is left enabled, so dragging the cursor into a
screen corner raises an exception that aborts the current action; the
engine catches it, resets the mouse state, and keeps running rather than
dying silently.

**What has and hasn't been verified for Mouse mode:** the full pinch →
click/double-click/right-click/drag/scroll state machine is covered by 11
passing unit tests against a fake OS-actions backend (so no test run ever
moved a real cursor). Live-camera verification in this session confirmed
the engine starts/stops cleanly, mode-switches correctly, and — critically
— fires zero OS actions when no hand is in frame (the core "no accidental
input" requirement). Actually moving the OS cursor and clicking with a real
hand in front of the camera has **not** been exercised by a human yet; do
that before relying on it.

## Known limitations

- Single-hand only in the MVP (multi-hand input is not evaluated).
- Gesture set is limited to what the pretrained MediaPipe model supports —
  no custom-trained gestures.
- Lighting and distance from the camera affect recognition reliability;
  see the test plan below for what was actually measured.
- Desktop-level automation (real OS keypresses, media controls) is **not**
  implemented — commands only act on the in-app demo state, by design (see
  the project's safety constraints on gesture-triggered system actions).
- This is not a substitute for dedicated assistive technology; it has not
  been evaluated with real target users.

## Test plan

| # | Test | What it checks | Result |
|---|---|---|---|
| 1 | Basic recognition | Each supported gesture, normal lighting | **Partially verified.** Ran the app live against a real webcam; `Open_Palm` and `Closed_Fist` were both correctly recognized and stabilized in that session (see event log below). `Thumb_Up`/`Victory`/`ILoveYou` were exercised through the command path via manual demo mode, not re-verified against the live camera in this session — do that before a hackathon demo. |
| 2 | Distance | Hand near vs. far from camera | Not yet tested — needs a human tester varying distance. |
| 3 | Lighting | Bright / normal / dim indoor lighting | Not yet tested — needs a human tester varying lighting. |
| 4 | Gesture transitions | Switching gestures doesn't repeat-fire the old command | **Verified.** During live testing, `Open_Palm` fired exactly one `pause` event (not once per frame while held), confirming the stabilizer does not re-trigger on a sustained gesture. |
| 5 | Stabilization | Brief vs. sustained gesture holds | **Verified.** `tests/test_stabilization.py` (6 tests, all passing) covers: below-confidence rejection, no fire before the stability window elapses, no re-fire while held + in cooldown, timer reset on gesture switch, reset when the hand disappears, and cooldown after release/reacquire. |
| 6 | Camera failure | Disconnect camera mid-session | Not yet tested — requires physically disconnecting the webcam. `camera.py` reports a clear error and `app.py` shows it without crashing if `cv2.VideoCapture` fails to open or read. |
| 7 | Pause/resume | No commands fire while paused | **Verified both ways.** Unit-tested in `tests/test_gesture_controller.py` (disabled controller blocks execution without calling the handler), and confirmed live: showing `Open_Palm` toggled pause on, and a subsequent `Closed_Fist` was logged with status `blocked` instead of executing. |
| 8 | Demo fallback | App usable via manual buttons with no camera | **Verified.** With the camera stopped, the Next/Back/Confirm/Reset buttons in "Manual demo mode" correctly drove the in-app demo card state and event log. |

Measured in this session: recognition pipeline ran at **~30 FPS** (OpenCV read + MediaPipe
inference, no display overhead) in a 5-second headless loop with no hand in frame — zero false
positives. Recognition-to-command latency averaged **568ms** over 2 live-camera triggers, consistent
with the default 500ms stability window plus normal per-frame variance.

Do not fill in measured numbers without actually running the test — see
`DEVELOPMENT RULES` in the project brief: never fabricate results. Tests 1 (full gesture set), 2, 3,
and 6 still need a human in front of the camera before a hackathon demo.

## Progress checklist

Tracked against the advanced-features roadmap's 8 priorities (spatial
mouse, app launcher, spatial keyboard, dynamic gestures, Magic Mode,
expressive signs, face+hand interaction, unified modes).

**Priority 1 — Spatial mouse: implemented and unit-tested, not yet
human-verified live.**
- [x] Index-finger pointer with configurable active region, mirroring, and exponential smoothing (`core/pointer_filter.py`, `core/mouse_controller.py`)
- [x] Click (pinch + release, debounced — holding doesn't repeat-click)
- [x] Double-click (two quick pinches in roughly the same spot, configurable window)
- [x] Right-click (distinct thumb+middle pinch)
- [x] Drag and drop (hold pinch past a threshold while moving; releases cleanly on hand loss)
- [x] Scroll (two-finger pose + vertical movement)
- [x] Mouse-mode sidebar controls: enable/disable per-action, sensitivity, smoothing, mirror
- [x] 11 unit tests against a fake OS-actions backend — real cursor never moved by a test
- [x] Background `InteractionEngine` thread so the pointer tracks real camera FPS instead of Streamlit's ~6-7fps rerun cadence
- [x] Live-verified: engine starts/stops cleanly, mode-switching works, **zero OS actions fire with no hand in frame**
- [ ] **Not yet verified: an actual human moving the cursor and clicking with a real hand.** I have no hands to test this with myself — try it and tune sensitivity/smoothing to taste.
- [x] Checkpoint committed locally; a camera-contention issue hit mid-session (another app had the webcam, causing 1fps reads and corrupted frames) — confirmed external, not a GestureBridge bug, and had cleared by the end of the session

**Priorities 2-7 — Application launcher, spatial keyboard, dynamic gestures,
Magic Mode, expressive hand signs, face+hand interaction: not started.**
This is a genuinely large scope (the roadmap itself lays out 10 implementation
phases); Priority 1 alone — done properly with real tests, not just code that
compiles — was the right-sized unit of work to land solidly in one pass
rather than sketching all seven remaining priorities shallowly. See the
roadmap's own "Implementation order" for the suggested next phase (D: spatial
keyboard, then E: app launcher).

**Priority 8 — Unified interaction modes: partially done.** A `Mode` selector
(Navigation / Mouse / Paused) exists and is enforced at the engine level —
switching modes resets the other mode's in-flight gesture state (a held
pinch doesn't carry into Navigation mode, a half-stabilized gesture doesn't
carry into Mouse mode), and only one mode's actions can fire at a time. The
remaining modes (Keyboard, Launcher, Expressive, Magic, Face+Hand) don't
exist yet to integrate into this switcher.

**Earlier MVP work (still intact, Navigation mode unchanged):**
- [x] Camera open/read/release with clear error reporting (`core/camera.py`)
- [x] MediaPipe GestureRecognizer wrapper, auto-downloads the pretrained model on first run (`core/recognizer.py`)
- [x] Stabilization: hold-to-confirm + cooldown, 6/6 unit tests passing (`core/stabilization.py`)
- [x] Gesture → command mapping, enable/disable gating, remap support (`core/gesture_controller.py`)
- [x] Full Streamlit UI: header, live feed, sidebar controls, gesture mapping panel, event history, analytics, manual fallback demo
- [x] Verified end-to-end against a real webcam in an earlier pass of this session; 3 real UI-staleness/leak bugs found and fixed then (see git history)

**Known bugs:** none open.

**To run it:** `streamlit run app.py` (see Setup/Running above).

**Demo readiness:** Navigation mode is demonstrable end-to-end as before.
Mouse mode's code and unit tests are solid, but needs a human to actually
try moving the cursor and clicking before calling it demo-ready — sensitivity
and smoothing defaults are reasonable guesses, not tuned against a real hand.

**Next highest-priority task:** get a human to try Mouse mode live and tune
it, then continue to Priority 2/3 (app launcher, spatial keyboard) per the
roadmap's implementation order.

## Troubleshooting

- **"mediapipe is not installed"** — you're likely on an unsupported Python
  version. Use 3.11–3.13.
- **Camera won't open** — close any other app using the webcam (Zoom,
  Teams, another browser tab), and check OS camera permissions.
- **Model download fails on first run** — `recognizer.py` downloads
  `gesture_recognizer.task` from Google's model storage on first use and
  caches it in `assets/`. Requires an internet connection once; after that
  it runs fully offline.
- **Camera feed is slow, frozen, or visibly corrupted/noisy** — another
  application likely has the webcam open (another video-call app, the OS
  camera app, a second browser tab). This showed up during development as
  a drop to ~1fps and torn/corrupted frames; it was confirmed external to
  GestureBridge by testing raw `cv2.VideoCapture` directly. Close other
  apps using the camera and restart tracking.
- **Mouse mode does nothing** — check the sidebar says "Mouse mode" is
  available, not "Unavailable: pyautogui failed to initialize"; that means
  `pyautogui` couldn't initialize on this machine (uncommon, but possible
  in a locked-down or headless environment).
- **Pointer feels laggy or jittery** — raise the Smoothing slider for less
  jitter (more lag), or lower it for a snappier but shakier pointer; raise
  Pointer sensitivity if you have to move your hand too far to cross the
  screen.
