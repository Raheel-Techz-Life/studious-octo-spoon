"""Optional local text-to-speech feedback via pyttsx3. Fails silently and
disables itself if no TTS engine is available on the machine - audio is a
nice-to-have, never a requirement for the app to run.
"""

from __future__ import annotations

import threading


class AudioFeedback:
    def __init__(self):
        self.available = False
        self._engine = None
        try:
            import pyttsx3
            self._engine = pyttsx3.init()
            self.available = True
        except Exception:
            self.available = False

    def speak(self, text: str) -> None:
        if not self.available or self._engine is None:
            return
        # Run in a thread so TTS never blocks the Streamlit rerun / camera loop.
        threading.Thread(target=self._speak_sync, args=(text,), daemon=True).start()

    def _speak_sync(self, text: str) -> None:
        try:
            self._engine.say(text)
            self._engine.runAndWait()
        except Exception:
            pass
