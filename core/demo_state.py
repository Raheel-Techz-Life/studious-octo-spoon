"""Navigation mode's demo-card state (which card is showing, whether it's
confirmed) as a plain, lock-protected object - not `st.session_state`.

Why this exists: Navigation-mode gesture handlers run on
InteractionEngine's background thread (see interaction_engine.py), but
Streamlit's `st.session_state` requires an active ScriptRunContext that
only exists on the thread actually running the Streamlit script. Touching
`st.session_state` from any other thread - even just reading it - raises
immediately and silently kills that thread (confirmed in practice: it
crashed the tracking loop with a KeyError the moment a Next/Back/Confirm/
Reset gesture fired, which looked like "tracking randomly stops" from the
UI with no visible error). This class is deliberately NOT stored inside
session_state's own machinery; app.py keeps a bare reference to it, and
the background thread calls its methods directly, never touching
`st.session_state` at all.
"""

from __future__ import annotations

import threading


class DemoState:
    def __init__(self, card_count: int):
        self._lock = threading.Lock()
        self._card_count = card_count
        self.index = 0
        self.confirmed = False

    def next(self) -> None:
        with self._lock:
            self.index = min(self._card_count - 1, self.index + 1)

    def back(self) -> None:
        with self._lock:
            self.index = max(0, self.index - 1)

    def confirm(self) -> None:
        with self._lock:
            self.confirmed = True

    def reset(self) -> None:
        with self._lock:
            self.index = 0
            self.confirmed = False
