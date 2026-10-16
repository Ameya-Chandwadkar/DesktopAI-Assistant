"""Offline speech recognition with Whisper (via faster-whisper, CPU int8).

Much more accurate than Vosk's small model, especially with accents. Whisper is not a streaming
recogniser: audio is collected while the button is held and transcribed on release (about 1-3 s).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Callable

from .. import paths
from .vosk_backend import SAMPLE_RATE, SpeechError

log = logging.getLogger("nova.speech")

# Short vocabulary hint: makes Whisper prefer these words for ambiguous sounds ("notepad", not "not bad").
PROMPT = (
    "Desktop assistant commands: open Notepad, open VS Code, open Chrome, open YouTube, "
    "search YouTube for, find file, open file, number two."
)
MAX_SECONDS = 30
_MAX_BYTES = MAX_SECONDS * SAMPLE_RATE * 2
_MIN_PEAK = 60  # below this the clip is silence; don't let Whisper hallucinate words from it
_PREFERRED = ("whisper-small.en", "whisper-base.en")  # best first


def find_whisper_model() -> Path | None:
    """A downloaded Whisper model folder inside <data>/models (best available), else None."""
    root = paths.models_dir()
    found = {d.name: d for d in root.iterdir() if d.is_dir() and d.name.startswith("whisper-") and (d / "model.bin").is_file()}
    for name in _PREFERRED:
        if name in found:
            return found[name]
    return next(iter(sorted(found.values())), None)


def whisper_available() -> bool:
    import importlib.util

    return importlib.util.find_spec("faster_whisper") is not None


class _WhisperStream:
    def __init__(self, model: Any):
        self._model = model
        self._buf = bytearray()

    def feed(self, pcm16: bytes) -> str:
        if len(self._buf) < _MAX_BYTES:
            self._buf += pcm16
        return ""  # no live partials with Whisper

    def finish(self) -> str:
        import numpy as np

        pcm = np.frombuffer(bytes(self._buf), dtype=np.int16).astype(np.int32)
        if pcm.size < SAMPLE_RATE * 0.3:
            return ""
        peak = int(np.abs(pcm).max())
        if peak < _MIN_PEAK:
            return ""
        audio = pcm.astype(np.float32) / 32768.0
        if peak < 8000:  # quiet laptop mic: scale up (at most 10x) towards a healthy level
            audio *= min(0.5 * 32768 / peak, 10.0)
        segments, _info = self._model.transcribe(
            audio,
            language="en",
            beam_size=3,
            vad_filter=True,
            condition_on_previous_text=False,
            initial_prompt=PROMPT,
        )
        return " ".join(s.text.strip() for s in segments).strip()


class WhisperRecognizer:
    def __init__(self, model_path: Path, model_factory: Callable[[str], Any] | None = None):
        self._path = model_path
        self._factory = model_factory
        self._model: Any = None

    def load(self) -> None:
        """Slow (a few seconds). Call from a background thread."""
        try:
            if self._factory:
                self._model = self._factory(str(self._path))
            else:
                from faster_whisper import WhisperModel

                self._model = WhisperModel(
                    str(self._path), device="cpu", compute_type="int8", cpu_threads=min(8, os.cpu_count() or 4)
                )
        except ImportError as e:
            raise SpeechError("The 'faster-whisper' package isn't installed. Run: pip install -r requirements.txt") from e
        except Exception as e:
            raise SpeechError(f"Couldn't load the Whisper model at '{self._path}'. Is the download complete? ({e})") from e
        log.info("whisper model loaded: %s", self._path.name)

    def new_stream(self) -> _WhisperStream:
        if self._model is None:
            raise SpeechError("The speech model isn't loaded yet.")
        return _WhisperStream(self._model)
