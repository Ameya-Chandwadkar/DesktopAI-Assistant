"""Offline speech recognition with Vosk (CPU only; no network, no GPU needed)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Protocol

from .. import paths

log = logging.getLogger("nova.speech")

SAMPLE_RATE = 16000


class SpeechError(Exception):
    """A problem the user can act on (message is safe to show)."""


class RecognitionStream(Protocol):
    def feed(self, pcm16: bytes) -> str:
        """Feed 16 kHz mono int16 audio; returns the text recognised so far."""

    def finish(self) -> str:
        """Flush and return the full final text."""


class Recognizer(Protocol):
    def new_stream(self) -> RecognitionStream: ...


def find_model(configured: str = "") -> Path | None:
    """Locate a Vosk model folder: the configured one, else the best one in <data>/models."""
    if configured:
        p = Path(configured)
        return p if p.is_dir() else None
    root = paths.models_dir()
    candidates = sorted(d for d in root.iterdir() if d.is_dir() and (d / "am").is_dir())
    # Names sort so that full models ("vosk-model-en-...") come before "vosk-model-small-...".
    return candidates[0] if candidates else None


class _VoskStream:
    def __init__(self, vosk_module, model):
        self._rec = vosk_module.KaldiRecognizer(model, SAMPLE_RATE)
        self._done: list[str] = []

    def feed(self, pcm16: bytes) -> str:
        if self._rec.AcceptWaveform(pcm16):
            text = json.loads(self._rec.Result()).get("text", "")
            if text:
                self._done.append(text)
            return " ".join(self._done)
        partial = json.loads(self._rec.PartialResult()).get("partial", "")
        return " ".join([*self._done, partial]).strip()

    def finish(self) -> str:
        text = json.loads(self._rec.FinalResult()).get("text", "")
        if text:
            self._done.append(text)
        return " ".join(self._done).strip()


class VoskRecognizer:
    def __init__(self, model_path: Path):
        self._path = model_path
        self._vosk = None
        self._model = None

    def load(self) -> None:
        """Slow (1-3 s). Call from a background thread."""
        try:
            import vosk
        except ImportError as e:
            raise SpeechError("The 'vosk' package isn't installed. Run: pip install -r requirements.txt") from e
        try:
            vosk.SetLogLevel(-1)
            self._model = vosk.Model(str(self._path))
            self._vosk = vosk
        except Exception as e:
            raise SpeechError(f"Couldn't load the speech model at '{self._path}'. Is the download complete? ({e})") from e
        log.info("speech model loaded: %s", self._path.name)

    def new_stream(self) -> RecognitionStream:
        if self._model is None:
            raise SpeechError("The speech model isn't loaded yet.")
        return _VoskStream(self._vosk, self._model)
