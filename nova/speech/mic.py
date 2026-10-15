"""Microphone capture. Audio lives only in memory, chunk by chunk - it is never saved."""

from __future__ import annotations

import queue
from typing import Protocol

from .vosk_backend import SAMPLE_RATE

PRIVACY_HINT = (
    "Check Windows Settings > Privacy & security > Microphone: turn on 'Microphone access' "
    "and 'Let desktop apps access your microphone'."
)


class MicError(Exception):
    pass


class AudioSource(Protocol):
    def start(self) -> None: ...
    def read(self, timeout: float) -> bytes | None: ...
    def stop(self) -> None: ...


def list_input_devices() -> list[str]:
    """Names of input devices; empty if none or if audio isn't available."""
    try:
        import sounddevice as sd

        return [d["name"] for d in sd.query_devices() if d["max_input_channels"] > 0]
    except Exception:
        return []


class MicCapture:
    def __init__(self, device_name: str = "", blocksize: int = 3200):
        self._wanted = device_name.strip().lower()
        self._blocksize = blocksize  # 0.2 s at 16 kHz
        self._q: queue.Queue[bytes] = queue.Queue()
        self._stream = None

    def _pick_device(self, sd) -> int | None:
        if not self._wanted:
            return None  # system default input
        for idx, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0 and self._wanted in d["name"].lower():
                return idx
        raise MicError(f"Microphone '{self._wanted}' was not found. Pick another in Settings > Speech.")

    def start(self) -> None:
        try:
            import sounddevice as sd
        except (ImportError, OSError) as e:
            raise MicError(f"Audio support isn't available ({e}). Run: pip install -r requirements.txt") from e
        try:
            if not any(d["max_input_channels"] > 0 for d in sd.query_devices()):
                raise MicError("No microphone was found. Plug one in or enable it in Windows Sound settings.")
            device = self._pick_device(sd)

            def callback(indata, frames, time_info, status):
                self._q.put(bytes(indata))

            self._stream = sd.RawInputStream(
                samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                blocksize=self._blocksize, device=device, callback=callback,
            )
            self._stream.start()
        except MicError:
            raise
        except Exception as e:  # PortAudioError and friends
            raise MicError(f"Couldn't open the microphone: {e}. {PRIVACY_HINT}") from e

    def read(self, timeout: float = 0.1) -> bytes | None:
        try:
            return self._q.get(timeout=timeout)
        except queue.Empty:
            return None

    def stop(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
