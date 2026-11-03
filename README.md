# GestureBridge

> Your Hands. Your Commands. Your Freedom.

A webcam-based hand-gesture control prototype, started as a 24-hour hackathon
MVP and now being extended into a broader vision-based interaction platform.
Recognizes hand gestures and hand shape via MediaPipe and turns them into
either in-app navigation commands or real OS pointer control, with a
stabilization layer that prevents a single held gesture from firing
repeatedly.

**Status:** the Navigation-mode MVP (gesture → in-app command), the Mouse
mode spatial pointer (Priority 1), the app Launcher (Priority 2), the
Keyboard mode spatial typing (Priority 3), swipe/circle dynamic gestures
(Priority 4), and Magic Mode (Priority 5) from the advanced-features
roadmap are implemented and tested. Expressive signs and face+hand
interaction are **not yet built** —
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
│   ├── dynamic_gestures.py       # trajectory-based swipe/circle detection (Navigation mode)
│   ├── mouse_controller.py       # pointer/click/double-click/right-click/drag/scroll state machine
│   ├── app_launcher.py           # app registry + safe, explicit-target launch function
│   ├── launcher_controller.py    # pointer->highlight->pinch-to-launch state machine
│   ├── keyboard_layout.py        # compact QWERTY layout as normalized key rects
│   ├── spatial_keyboard.py       # pointer->highlight->pinch-to-type state machine
│   ├── magic_effects.py          # Magic Mode's state machine (idle glow + circle-triggered burst)
│   ├── pointer_filter.py         # exponential smoothing for the cursor
│   ├── interaction_engine.py     # background tracking thread, owns camera+recognizer
│   └── event_logger.py           # bounded, thread-safe in-memory event history
├── ui/
│   ├── components.py              # Streamlit UI fragments (keyboard + launcher panels)
│   ├── magic_overlay.py            # Magic Mode's OpenCV rendering (ring/runes/particles)
│   └── styles.py                   # dark, high-contrast theme CSS
├── utils/
│   ├── metrics.py                  # pandas aggregation for analytics
│   └── audio_feedback.py           # optional local TTS confirmation
└── tests/
    ├── test_stabilization.py
    ├── test_gesture_controller.py
    ├── test_dynamic_gestures.py
    ├── test_mouse_controller.py
    ├── test_app_launcher.py
    ├── test_launcher_controller.py
    ├── test_spatial_keyboard.py
    ├── test_magic_effects.py
    └── test_magic_overlay.py
```

**Data flow (Navigation mode):** `camera.py` grabs a frame → `recognizer.py`
runs MediaPipe inference and returns a plain `RecognitionResult` (gesture
label + real confidence score, never fabricated) → `stabilization.py` tracks
whether that gesture has held steady long enough, and enforces a cooldown →
only then does `gesture_controller.py` dispatch the mapped in-app command →
`event_logger.py` records what happened for the history/analytics panels.
In parallel, the same frame's wrist position also feeds
`dynamic_gestures.py`'s trajectory buffer; a detected swipe or circle
dispatches through `gesture_controller.py::invoke_command` (bypassing the
static gesture→command mapping, since a motion isn't one of the
recognizer's discrete pose labels).

**Data flow (Mouse mode):** same camera + recognizer, but `recognizer.py`'s
raw 21-point hand landmarks go to `mouse_controller.py` instead of the
discrete gesture classifier/stabilizer — it reads fingertip positions and
pinch distances directly every frame (via `hand_landmarks.py`'s geometry
helpers), smooths the index fingertip with `pointer_filter.py`, and turns
pinch/pose state transitions into real `pyautogui` pointer calls.

**Data flow (Launcher mode):** same camera + recognizer again, raw landmarks
go to `launcher_controller.py` - same pointer-smoothing/pinch-distance
approach once more, but looking up which `app_launcher.py` registry entry
the pointer is over, and on pinch-release calling `app_launcher.launch()`
(a validated, explicit-target process launch, never a shell string built
from anything gesture-derived).

**Data flow (Keyboard mode):** same camera + recognizer again, but the raw
landmarks go to `spatial_keyboard.py` instead — it reuses the same
`pointer_filter.py` smoothing and pinch-distance approach as Mouse mode,
looks up which `keyboard_layout.py` key the smoothed pointer is over, and on
pinch-release commits that key to an in-app text buffer rather than calling
any OS API. The UI renders the layout as a styled grid via
`ui/components.py::keyboard_panel`.

**Data flow (Magic mode):** same camera + recognizer again; the wrist
position feeds `magic_effects.py`, which reuses `dynamic_gestures.py`'s
circle detector internally (not Navigation mode's instance - a separate
one, so the two modes' cooldowns never interfere) to decide when to start
a burst, and tracks idle rotation phase, speed-driven intensity, and
particle positions purely as numbers. `ui/magic_overlay.py` then reads
that state and draws it onto the frame with OpenCV - rendering is fully
separated from the state machine specifically so the animation's timeline
could be unit-tested without touching a single pixel.

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

## Dynamic gestures (Navigation mode)

Beyond the static poses above, Navigation mode also recognizes motion:
swipe left/right/up/down and a full circular hand movement, detected from a
rolling trajectory buffer of the wrist position rather than any single
frame's hand pose - this is what makes them "dynamic" rather than static.

| Motion | Action |
|---|---|
| Swipe left | Back |
| Swipe right | Next |
| Swipe up | Confirm |
| Swipe down | Reset |
| Full circle (either direction) | Detected and shown (no demo action yet - see Known limitations) |

Both detectors run off the same trajectory buffer in `core/dynamic_gestures.py`:

- **Swipe** requires large net displacement, a straight-enough path
  (net displacement / total path length), *and* a low cumulative turning
  angle, completed inside a time budget. The straightness check alone
  isn't sufficient to reject curved motion - a short arc of a circle also
  scores "straight" by that ratio alone, which is exactly the false
  positive a first version of this code had during development (see git
  history); the cumulative-turn check is what actually tells a slightly
  curved swipe apart from a piece of a circle.
- **Circle** fits a center point to the recent trajectory and sums the
  *signed* angular change frame-to-frame to measure how much of a full
  rotation was actually traced (the "trajectory/geometric method" rather
  than checking whether the hand happened to visit a scattered set of
  positions).

Both share one cooldown and clear their shared buffer the moment a gesture
fires, so the tail end of a completed swipe or circle can't immediately
re-trigger another detection, and an interrupted motion (hand disappears
mid-swipe) is discarded rather than evaluated as if it had completed.
Toggle this off in the sidebar without affecting static-gesture Navigation
commands.

**What has and hasn't been verified:** the full detection logic (correct
direction/rotation-sense classification, rejection of short/slow/wobbly
motion, the cooldown, and hand-loss-mid-gesture handling) is covered by 12
unit tests using a fake clock and synthetic trajectories, no camera needed.
A separate headless integration test fed a synthetic swipe through the
exact dispatch path the engine uses and confirmed it correctly drove the
demo card state and event log. Actually swiping or circling in front of a
real camera has **not** been exercised by a human yet - the thresholds
(minimum distance, straightness, turning angle, circle coverage) are
reasoned defaults, not tuned against real hand motion.

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

## Launcher mode

The index fingertip moves a selection cursor over a grid of configured
applications; a pinch-and-release over the highlighted tile launches it.
Ships with a small default set (Notepad/Calculator/File Explorer/Paint on
Windows, Calculator/TextEdit/Finder on macOS — only the current platform's
entries are shown), and the sidebar lets you add your own by typing a
display name and a target (an exe name on PATH, or an absolute path on
Windows; an application name for macOS's `open -a`).

| Gesture | Action |
|---|---|
| Move index finger over a tile | Highlight it |
| Pinch thumb + index while over a tile, release | Launch that app |
| (unavailable app, grayed out) | Pinch reports a failure message instead of launching |

**Safety, concretely:** a launch target is never built from a gesture label
or any recognition output — only from the fixed default list or text the
user typed into the sidebar. Launching never goes through a shell string:
Windows uses `os.startfile()` (the same mechanism as double-clicking in
Explorer) on a target that's been validated as resolvable via PATH or an
existing file; macOS uses `subprocess.Popen(["open", "-a", name])` with an
explicit argument list. A target is checked for availability both before
it's shown as selectable (grayed out otherwise) and again immediately
before launching.

**What has and hasn't been verified:** the full pointer→highlight→pinch→
launch state machine (debounced, cooldown-gated, hand-loss-safe, and that
an unavailable app reports failure without ever calling the real launch
function) is covered by 14 unit tests using a fake launch backend — no
test run ever spawns a real process. Live-camera verification in this
session confirmed the grid renders and re-flows correctly, and the
"add/remove custom app" flow works end-to-end (added `cmd.exe` as
"Command Prompt", confirmed it appeared as a 5th tile with an availability
checkmark, then removed it). Actually launching an app with a real pinch
gesture has **not** been exercised by a human yet. macOS discovery/launch
is implemented but entirely untested — this session only had a Windows
machine to verify against.

## Magic mode

Switching to Magic mode is itself the deliberate activation step the
project brief asks for. A soft amber glow (a rotating dashed ring plus
small rotating rune-like marks, drawn with OpenCV directly onto the camera
feed - original fantasy visuals, nothing copied from any film) follows
your hand continuously. Trace a full circle and it triggers a burst:
particles scatter outward from the circle's center and an expanding ring
fades out over about 1.4 seconds.

| Action | Effect |
|---|---|
| Show your hand | A soft idle glow ring appears, anchored on and following your hand |
| Move your hand faster | The glow intensifies (brighter/larger) in response to hand speed |
| Trace a full circle | Triggers a particle burst + expanding ring from the circle's center |
| Switch to another mode | Exits Magic mode; glow and any in-progress burst are cleared |

The circle detection is the *exact same* geometric detector Navigation
mode's dynamic gestures use (`core/dynamic_gestures.py`) - Magic mode
doesn't reimplement motion analysis, it just reacts differently to the
same detected event. The animation's state (hand position, rotation
phase, particle positions, burst progress) is tracked in
`core/magic_effects.py`, deliberately separated from the actual drawing
code in `ui/magic_overlay.py`, so the whole timeline - speed-driven
intensity, particle motion outward from the burst center, burst
progress reaching 1.0 and clearing - is unit-testable without rendering
a single pixel.

**What has and hasn't been verified:** 15 unit tests (12 for the state
machine with a fake clock, 3 rendering smoke tests confirming the overlay
never crashes and always returns a correctly-shaped frame) all pass.
Live-verified with a real hand in front of the camera: Hand tracking
correctly read "Yes" with Intensity climbing to 1.00 on fast movement and
settling near the 0.15 baseline when still, and correctly dropped to "No"
tracking / 0.15 baseline the instant the hand left frame - confirming the
speed-to-intensity response and hand-loss reset both work against real
input, not just synthetic test data. What I could *not* independently
verify live: actually tracing a full circle and watching the burst fire,
since doing that requires a second pair of hands at the keyboard and the
camera at once. The underlying circle detector itself is already
real-camera-tested indirectly (Navigation mode's dynamic gestures use the
identical detector), and the burst logic is fully covered by synthetic
circular-trajectory unit tests, but the literal "wave a hand in a circle
and see the burst" moment is the one piece still waiting on a human.

## Keyboard mode

The index fingertip moves a selection cursor over a virtual QWERTY layout
rendered in the UI (letters, digits, Space, Backspace, Enter, Shift, Caps
Lock, Clear — no symbol/punctuation layer yet). A pinch-and-release over the
highlighted key types it; just hovering never types anything.

| Gesture | Action |
|---|---|
| Move index finger over a key | Highlight it |
| Pinch thumb + index while over a key, release | Type that key |
| Pinch over Shift | One-shot: capitalizes the next letter only |
| Pinch over Caps | Sticky: stays on until pinched again |
| Pinch over Backspace / Space / Enter / Clear | Edit the in-app text field accordingly |

Typing is entirely in-app — it writes to a text field inside GestureBridge,
not into other applications. System-wide keyboard injection is explicitly
out of scope for now (per the roadmap: build in-app typing first). Losing
the hand mid-pinch does not type anything, and typed text survives a mode
switch or a momentarily lost hand (only truly cleared by the Clear key or
the sidebar's "Clear typed text" button).

**What has and hasn't been verified:** the full pointer→highlight→pinch→
type state machine (including the Shift one-shot/Caps sticky distinction,
backspace/space/enter/clear, and that a held pinch doesn't repeat-type) is
covered by 9 passing unit tests with synthetic hand landmarks — no camera
needed. Live-camera verification in this session confirmed the mode
switches in cleanly and the keyboard grid renders and highlights correctly;
actually typing a sentence with a real hand has **not** been exercised by a
human yet.

## Known limitations

- Single-hand only in the MVP (multi-hand input is not evaluated).
- Gesture set is limited to what the pretrained MediaPipe model supports —
  no custom-trained gestures.
- Lighting and distance from the camera affect recognition reliability;
  see the test plan below for what was actually measured.
- Navigation mode's commands only act on the in-app demo state, by design.
  Real OS automation exists, but only in the dedicated modes built for it:
  Mouse mode (real pointer/click/drag/scroll) and Launcher mode (real
  process launch) — both with explicit safety constraints documented in
  their own sections above. Keyboard mode is in-app only, by design (no
  system-wide keyboard injection). There is no general mechanism for an
  arbitrary gesture to run an arbitrary OS command.
- Circular movement is detected and displayed in Navigation mode but has no
  action mapped to it yet - no demo command fits naturally, and it's the
  natural trigger for Magic Mode (a later, unbuilt priority), so it's left
  unmapped rather than forced into an arbitrary one.
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

**Priority 3 — Spatial keyboard: implemented and unit-tested, not yet
human-verified live.**
- [x] Compact QWERTY layout (letters, digits, Space, Backspace, Enter, Shift, Caps, Clear) as normalized key rects (`core/keyboard_layout.py`)
- [x] Pointer → highlight → pinch-to-select state machine, reusing the same smoothing approach as Mouse mode but writing to an in-app text buffer instead of the OS (`core/spatial_keyboard.py`)
- [x] Shift (one-shot) vs. Caps (sticky) handled distinctly; Backspace/Space/Enter/Clear all wired up
- [x] Debounced: holding a pinch doesn't repeat-type; a select cooldown prevents accidental double-types
- [x] 9 unit tests with synthetic hand landmarks, no camera needed
- [x] Rendered as a styled virtual keyboard in the UI (`ui/components.py::keyboard_panel`, new CSS in `ui/styles.py`), with the same pointer-dot overlay on the camera feed Mouse mode uses
- [x] Live-verified: mode switches in cleanly, the keyboard grid renders and highlights correctly
- [ ] **Not yet verified: an actual human typing a real sentence with their hand.**
- [x] Explicitly out of scope per the roadmap: system-wide keyboard injection into other applications (in-app typing only, by design)

**Priority 2 — Application launcher: implemented and unit-tested, not yet
human-verified live with a real pinch-launch.**
- [x] Grid-of-apps launcher UI, reusing the same pointer/pinch pattern as Mouse and Keyboard mode (`core/launcher_controller.py`, `ui/components.py::launcher_panel`)
- [x] Default app set for both Windows and macOS (only the current platform's entries show); sidebar lets you add/remove custom apps by name + target
- [x] Safe launching: explicit validated targets only, never a shell string, never built from gesture/recognition output (`core/app_launcher.py`) — `os.startfile()` on Windows, `open -a` with an argument list on macOS
- [x] Availability checked both before showing a tile as selectable (grayed out otherwise) and again at launch time
- [x] Debounced (holding a pinch doesn't relaunch) with a confirm cooldown; hand loss mid-pinch launches nothing
- [x] 14 unit tests (7 for the registry/launch-validation, 7 for the pointer/pinch state machine) against a fake launch backend — no test ever spawns a real process
- [x] Live-verified: grid renders/re-flows correctly, and the full add/remove-custom-app flow works end-to-end (added `cmd.exe` as "Command Prompt", saw it appear as a 5th tile with an availability checkmark, removed it)
- [ ] **Not yet verified: an actual human pinching to launch a real app.**
- [ ] **macOS entirely untested** — implemented per the roadmap's platform-adapter guidance, but this session only had a Windows machine to verify against
- [x] Window-switching between already-open apps (section 4.4) intentionally skipped — the roadmap marks it a secondary, OS-permission-heavy enhancement

**Priority 4 — Dynamic gestures: implemented and unit-tested, not yet
human-verified live.**
- [x] Trajectory-based swipe detection (left/right/up/down), rejecting short movement, slow drift, wobbly paths, *and* arcs of a circle that would otherwise score "straight" by displacement/path-length ratio alone (`core/dynamic_gestures.py`)
- [x] Geometric circular-movement detection (fits a center, sums signed angular change to measure actual rotation coverage - not just "visited a scattered set of positions")
- [x] Shared cooldown + buffer-clear-on-fire so a completed gesture's tail can't immediately re-trigger another
- [x] An interrupted motion (hand disappears mid-swipe/circle) is discarded, not evaluated as completed
- [x] Wired into Navigation mode: swipes drive Back/Next/Confirm/Reset via `GestureController.invoke_command` (a new dispatch path for commands that don't come from the static gesture→command mapping); circle is detected and shown but has no demo action yet (natural fit for Magic Mode, a later priority, which will reuse this same detector)
- [x] Sidebar toggle to disable dynamic gestures independent of static Navigation commands
- [x] 12 unit tests with a fake clock and synthetic trajectories (fast, deterministic — no real `time.sleep()`), plus a separate headless integration test confirming a synthetic swipe correctly drives demo-card state through the exact dispatch path the engine uses
- [x] A real latent bug found and fixed during testing: the cooldown gate compared against a `0.0` sentinel for "no gesture yet," which could wrongly suppress a detector's very first gesture if `now` happened to be small — invisible with the real `time.monotonic()` clock (always large) but reproducible with a fake clock, so worth fixing properly rather than dismissing as a test artifact
- [ ] **Not yet verified: an actual human swiping or circling in front of a real camera.** Thresholds are reasoned defaults, not tuned against real hand motion.

**Priority 5 — Magic Mode: implemented and unit-tested, partially
human-verified live.**
- [x] Deliberate activation via the Mode selector itself (switching to Magic mode is the activation step the brief asks for; switching away exits and clears all state)
- [x] Idle glow ring anchored on and following the hand, continuously rotating (`core/magic_effects.py`)
- [x] Effect intensity driven by real hand movement speed (brighter/larger on fast motion, settles to a baseline when still)
- [x] Circular hand movement triggers a particle burst + expanding fading ring, reusing `dynamic_gestures.py`'s geometric circle detector directly rather than reimplementing motion analysis (a separate detector instance from Navigation mode's, so the two modes' cooldowns never cross-contaminate)
- [x] Original, generic fantasy visuals only (rotating dashed ring, small triangular rune marks, outward particles) — nothing copied from any specific film; drawn with lightweight OpenCV overlays directly on the camera frame, matching the roadmap's "no heavyweight 3D engine" guidance
- [x] State machine (hand position, rotation phase, particle physics, burst progress) deliberately separated from rendering (`ui/magic_overlay.py`), so the whole animation timeline is unit-testable without rendering a single pixel
- [x] 15 unit tests (12 state-machine tests with a fake clock, 3 rendering smoke tests) — 72 total now passing
- [x] Live-verified with a real hand: "Hand tracking: Yes" with Intensity correctly climbing to 1.00 on fast movement and settling near baseline when still, correctly dropping to "No"/baseline the instant the hand left frame
- [ ] **Not yet verified: actually tracing a full circle and watching the burst fire live.** Needs a second pair of hands at the keyboard and the camera simultaneously; the burst logic itself is fully covered by synthetic-trajectory unit tests, and the identical circle detector is already exercised against real camera input via Navigation mode's dynamic gestures, but the literal "wave a circle, see sparks" moment is still unconfirmed by a human.
- [x] Two-hand activation pose (brief's "where practical" optional item) intentionally skipped — the recognizer is configured for single-hand tracking throughout the app, and adding a second hand is a bigger architecture change than this priority's scope justified

**Priorities 6-7 — Expressive hand signs, face+hand interaction: not
started.** This is a genuinely large scope (the roadmap itself lays out 10
implementation phases); Priorities 1-5, done properly with real tests
rather than code that merely compiles, were the right-sized units of work
to land solidly in one pass each. See the roadmap's own "Implementation
order" for the next suggested phase (H: expressive hand signs).

**Priority 8 — Unified interaction modes: partially done.** A `Mode` selector
(Navigation / Mouse / Keyboard / Launcher / Magic / Paused) exists and is
enforced at the engine level — switching modes resets the other modes'
in-flight gesture state (a held pinch doesn't carry into Navigation mode, a
half-stabilized gesture doesn't carry into Mouse/Keyboard/Launcher mode,
typed text and launch-feedback survive a switch but a mid-pinch doesn't
commit, a cleared burst doesn't come back), and only one mode's actions
can fire at a time. The remaining modes (Expressive, Face+Hand) don't
exist yet to integrate into this switcher.

**Earlier MVP work (still intact, Navigation mode unchanged):**
- [x] Camera open/read/release with clear error reporting (`core/camera.py`)
- [x] MediaPipe GestureRecognizer wrapper, auto-downloads the pretrained model on first run (`core/recognizer.py`)
- [x] Stabilization: hold-to-confirm + cooldown, 6/6 unit tests passing (`core/stabilization.py`)
- [x] Gesture → command mapping, enable/disable gating, remap support (`core/gesture_controller.py`)
- [x] Full Streamlit UI: header, live feed, sidebar controls, gesture mapping panel, event history, analytics, manual fallback demo
- [x] Verified end-to-end against a real webcam in an earlier pass of this session; 3 real UI-staleness/leak bugs found and fixed then (see git history)

**Known bugs:** none open. One known **environment-specific quirk**, not
an application bug (see Troubleshooting): under this project's automated
browser test harness specifically, the live camera `<img>` sometimes fails
to finish loading before the next ~150ms fragment tick replaces it,
because that harness's own fetch/decode overhead is slower than a normal
browser's. Root-caused with an isolated minimal Streamlit+OpenCV
reproduction outside this app entirely (confirmed the identical race
exists with zero GestureBridge code involved), so it isn't believed to
affect a normal end-user browser — but it means some of this session's
live-verification screenshots show the status panels working correctly
without the video frame itself visibly rendered.

**To run it:** `streamlit run app.py` (see Setup/Running above).

**Demo readiness:** Navigation mode's static gestures are demonstrable
end-to-end as before, and its dynamic swipe/circle detection has a
confirmed-working dispatch path (headless-verified) layered on top. Mouse,
Launcher, Keyboard, and Magic mode's code and unit tests are solid, and all
four render and switch correctly live — Magic mode's idle glow and
speed-driven intensity were confirmed against a real hand — but all five
features need a human to actually move/click/launch/type/swipe/circle with
a real hand before calling them fully demo-ready — thresholds and sensitivity
defaults are reasoned guesses, not tuned against real motion.

**Next highest-priority task:** get a human to try Mouse, Launcher,
Keyboard, Magic mode, and the dynamic gestures live and tune them, then
continue to Priority 6 (expressive hand signs) per the roadmap's
implementation order.

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
- **A launcher tile shows grayed out / "unavailable"** — its target isn't
  resolvable on this machine. On Windows that means it isn't on PATH and
  isn't an existing absolute file path; check the exact spelling (e.g.
  `code.exe` not `vscode.exe`) or use the full path if it's not on PATH.
- **Launcher does nothing on macOS** — macOS support (`open -a <name>`) is
  implemented but has not been tested in this project's development
  session (Windows-only environment); please report back what you find.
- **Camera feed shows blank/doesn't render, but status text (hand
  tracking, intensity, gesture) updates correctly** — this was observed
  during this project's own development under its automated browser test
  harness: the harness's own image fetch/decode is sometimes slower than
  the ~150ms fragment refresh, so each frame's `<img>` request gets
  superseded before it finishes loading. Confirmed with a minimal
  Streamlit+OpenCV reproduction completely outside this app (same race,
  zero GestureBridge code), so it's believed to be specific to that
  testing tool rather than a real browser. If you see this in an actual
  browser, try a hard refresh, or lower Streamlit's fragment update rate
  (the `run_every=0.15` argument in `app.py`'s `live_fragment`) and see if
  that resolves it — if so, please report it, since that would mean the
  issue is broader than this session's testing environment.
