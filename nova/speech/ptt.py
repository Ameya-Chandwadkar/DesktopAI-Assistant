"""Push-to-talk: record while the button is held, recognise, report text. Qt-free."""

from __future__ import annotations

import array
import logging
import threading
from typing import Callable

from .mic import AudioSource, MicError, PRIVACY_HINT
from .vosk_backend import SAMPLE_RATE, Recognizer, SpeechError

log = logging.getLogger("nova.ptt")

MIN_SECONDS = 0.4
SILENCE_PEAK = 60  # int16 peak below this over the whole clip = the mic gave us silence


class PushToTalk:
    """Callbacks run on the worker thread; the UI layer forwards them as Qt signals."""

    def __init__(
        self,
        recognizer: Recognizer,
        source_factory: Callable[[], AudioSource],
        on_listening: Callable[[], None],
        on_partial: Callable[[str], None],
        on_final: Callable[[str], None],
        on_error: Callable[[str], None],
    ):
        self._recognizer = recognizer
        self._source_factory = source_factory
        self._on_listening = on_listening
        self._on_partial = on_partial
        self._on_final = on_final
        self._on_error = on_error
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> bool:
        if self.busy:
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="nova-ptt", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()

    # ------------------------------------------------------------------
    def _run(self) -> None:
        source = None
        try:
            stream = self._recognizer.new_stream()
            source = self._source_factory()
            source.start()
            self._on_listening()
            bytes_read, peak, last_partial, halted = 0, 0, "", False
            while True:
                stopping = self._stop.is_set()
                if stopping and not halted:
                    source.stop()  # stop capturing, then drain what's already buffered
                    halted = True
                chunk = source.read(0.05 if stopping else 0.1)
                if chunk is None:
                    if stopping:
                        break  # buffer drained after release
                    continue
                bytes_read += len(chunk)
                peak = max(peak, max((abs(s) for s in array.array("h", chunk)), default=0))
                partial = stream.feed(chunk)
                if partial and partial != last_partial:
                    last_partial = partial
                    self._on_partial(partial)
            text = stream.finish().strip()
            seconds = bytes_read / 2 / SAMPLE_RATE
            if seconds < MIN_SECONDS:
                self._on_error("That was too short - hold the button while you speak.")
            elif not text:
                if peak < SILENCE_PEAK:
                    self._on_error(f"I only heard silence. Is the right microphone selected and unmuted? {PRIVACY_HINT}")
                else:
                    self._on_error("I couldn't make out any words. Try again, a little closer to the mic.")
            else:
                self._on_final(text)
        except (MicError, SpeechError) as e:
            self._on_error(str(e))
        except Exception:
            log.exception("push-to-talk failed")
            self._on_error("Speech recognition hit an unexpected error. Details are in the log file.")
        finally:
            if source is not None:
                source.stop()
