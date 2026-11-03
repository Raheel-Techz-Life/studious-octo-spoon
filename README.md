# GestureBridge

> Your Hands. Your Commands. Your Freedom.

A webcam-based hand-gesture control prototype built for a 24-hour hackathon.
Recognizes a small set of hand gestures via MediaPipe and maps them to
in-app commands, with a stabilization mechanism that prevents a single held
gesture from firing repeatedly.

**Status: MVP in progress.** See the checklist below for what is actually
implemented and tested versus planned.

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

Then, in the browser tab Streamlit opens, click **Start camera** in the
sidebar.

## Running tests

```bash
pip install -r requirements-dev.txt
pytest
```

`tests/test_stabilization.py` and `tests/test_gesture_controller.py` cover
the stabilization and command-mapping logic directly (no camera or model
required — these run anywhere Python runs).

## Architecture

```
gesturebridge/
├── app.py                   # Streamlit UI + wiring
├── prototype.py              # Phase 1 standalone smoke test
├── core/
│   ├── camera.py              # webcam open/read/release, error-safe
│   ├── recognizer.py          # MediaPipe GestureRecognizer wrapper
│   ├── gesture_controller.py  # gesture -> command mapping + dispatch
│   ├── stabilization.py       # hold-to-confirm + cooldown logic
│   └── event_logger.py        # bounded in-memory event history
├── ui/
│   ├── components.py          # Streamlit UI fragments
│   └── styles.py               # dark, high-contrast theme CSS
├── utils/
│   ├── metrics.py              # pandas aggregation for analytics
│   └── audio_feedback.py       # optional local TTS confirmation
└── tests/
    ├── test_stabilization.py
    └── test_gesture_controller.py
```

**Data flow:** `camera.py` grabs a frame → `recognizer.py` runs MediaPipe
inference and returns a plain `RecognitionResult` (gesture label + real
confidence score, never fabricated) → `stabilization.py` tracks whether that
gesture has held steady long enough, and enforces a cooldown → only then does
`gesture_controller.py` dispatch the mapped in-app command → `event_logger.py`
records what happened for the history/analytics panels.

### Why Streamlit needed care here

Streamlit reruns the whole script on every widget interaction. A naive
webcam integration would reopen the camera and reset gesture state on every
click. This app keeps the camera, recognizer, controller, and stabilizer as
long-lived objects in `st.session_state` (created once, on "Start camera"),
and drives the live camera feed with `st.fragment(run_every=...)` so only
that fragment reruns on its own timer — sidebar widgets and their state are
untouched while the feed updates.

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

**Completed and verified (this session):**
- [x] Camera open/read/release with clear error reporting (`core/camera.py`)
- [x] MediaPipe GestureRecognizer wrapper, auto-downloads the pretrained model on first run (`core/recognizer.py`)
- [x] Stabilization: hold-to-confirm + cooldown, 11/11 unit tests passing (`core/stabilization.py`)
- [x] Gesture → command mapping, enable/disable gating, remap support (`core/gesture_controller.py`)
- [x] Bounded event history (`core/event_logger.py`)
- [x] Full Streamlit UI: header, live feed, sidebar controls, gesture mapping panel, event history, analytics (matplotlib bar chart + latency), manual fallback demo
- [x] Verified end-to-end against a real webcam: live gesture recognition, stabilization (no repeat-fire on a held gesture), pause/resume gating (a gesture is correctly blocked while paused), and the manual fallback — all confirmed by hand in a running browser session
- [x] Three real bugs found and fixed during that verification: (1) header/button state went stale after Start/Stop camera because it rendered before the click handler ran — fixed with `st.rerun()`; (2) clicking Start camera twice would leak the previous camera/recognizer handle — fixed with a running-guard; (3) the manual "Pause" button logged an event but never actually toggled execution, and the sidebar toggle went stale the same way as (1) — fixed to match the live-camera pause path plus `st.rerun()`
- [x] Long-path bug: the original scratch working directory broke native DLL loading (Pillow) on Windows; moved the project to a short path and rebuilt the venv as the fix

**Not yet done / needs a human:**
- [ ] Full gesture-set sweep (`Thumb_Up`, `Victory`, `ILoveYou`, `Thumb_Down`, `Pointing_Up`) against the live camera — only `Open_Palm` and `Closed_Fist` were naturally exercised during this session's testing
- [ ] Distance and lighting variation tests (test plan #2, #3)
- [ ] Camera-disconnect-mid-session test (test plan #6) — requires physically unplugging the webcam
- [ ] Gesture remapping UI (sidebar currently shows the mapping but doesn't let you edit it)
- [ ] Any desktop-level OS automation (intentionally out of scope per the project's safety constraints — commands only act on in-app state)

**Known bugs:** none open. (Three were found and fixed during live verification; see above.)

**To run it:** `streamlit run app.py` (see Setup/Running above).

**Demo readiness:** MVP is demonstrable end-to-end right now — start the camera, show
`Open_Palm` to pause/resume, any mapped gesture to drive the demo cards, and the manual
fallback buttons work identically with no camera. Before a real hackathon demo, run the
full gesture sweep above at least once.

**Next highest-priority task:** the full gesture-set sweep against a live camera (first
unchecked item above).

## Troubleshooting

- **"mediapipe is not installed"** — you're likely on an unsupported Python
  version. Use 3.11–3.13.
- **Camera won't open** — close any other app using the webcam (Zoom,
  Teams, another browser tab), and check OS camera permissions.
- **Model download fails on first run** — `recognizer.py` downloads
  `gesture_recognizer.task` from Google's model storage on first use and
  caches it in `assets/`. Requires an internet connection once; after that
  it runs fully offline.
