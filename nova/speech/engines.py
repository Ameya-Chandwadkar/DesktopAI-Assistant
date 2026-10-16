"""Chooses which speech engine to use on this PC."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import Settings
from .vosk_backend import VoskRecognizer, find_model
from .whisper_backend import WhisperRecognizer, find_whisper_model, whisper_available


@dataclass(frozen=True)
class EngineChoice:
    kind: str  # "whisper" | "vosk"
    path: Path

    @property
    def label(self) -> str:
        return f"{self.kind}: {self.path.name}"


def choose_engine(settings: Settings) -> EngineChoice | None:
    """'auto' prefers Whisper (more accurate) when a Whisper model is downloaded, else Vosk."""
    pref = settings.speech_engine
    if pref in ("auto", "whisper") and whisper_available():
        w = find_whisper_model()
        if w:
            return EngineChoice("whisper", w)
    if pref in ("auto", "vosk"):
        v = find_model(settings.vosk_model_path)
        if v:
            return EngineChoice("vosk", v)
    return None


def create_recognizer(choice: EngineChoice):
    return WhisperRecognizer(choice.path) if choice.kind == "whisper" else VoskRecognizer(choice.path)


def missing_message(settings: Settings) -> str:
    if settings.speech_engine == "whisper":
        return "No Whisper model found - typing still works. Run: python -m nova --download-model whisper-small, then restart NOVA."
    if settings.speech_engine == "vosk":
        return "No Vosk model found - typing still works. Run: python -m nova --download-model vosk-small, then restart NOVA."
    return "No speech model found - typing still works. Run: python -m nova --download-model whisper-small, then restart NOVA."
