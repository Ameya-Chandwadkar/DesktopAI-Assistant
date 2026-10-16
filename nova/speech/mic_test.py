"""`python -m nova --mic-test [DEVICE]`: records a few seconds IN MEMORY, shows the input level and
what the speech model heard, then says what is probably wrong. Nothing is saved to disk."""

from __future__ import annotations

import array
import math
import time
from typing import Callable

from .mic import AudioSource, MicCapture, MicError, PRIVACY_HINT, list_input_devices
from .vosk_backend import Recognizer, SpeechError

SILENT_PEAK = 60       # about -55 dBFS: effectively nothing arrived
QUIET_PEAK = 2000      # about -24 dBFS: speech peaks lower than this are too faint for good recognition
CLIP_PEAK = 32000


def dbfs(value: float) -> float:
    return 20 * math.log10(max(value, 1) / 32768)


def level_bar(peak: int, width: int = 24) -> str:
    filled = max(0, min(width, round((dbfs(peak) + 60) / 60 * width)))  # -60..0 dBFS
    return "#" * filled + "." * (width - filled)


def verdict(peak: int, text: str, have_model: bool) -> list[str]:
    if peak < SILENT_PEAK:
        return [
            "RESULT: no sound reached NOVA (the microphone gave silence).",
            "  - Windows privacy: " + PRIVACY_HINT,
            "  - Wrong device: run again with another one, e.g.  python -m nova --mic-test \"Headset\"",
            "  - Check the mic isn't muted (keyboard mic key / Sound settings > Input).",
        ]
    lines = []
    if peak < QUIET_PEAK:
        lines += [
            f"RESULT: the microphone works but is VERY QUIET (peak {dbfs(peak):.0f} dBFS).",
            "  - Settings > System > Sound > Input > your mic > set Input volume to 100.",
            "  - In the same page, turn off/try 'Audio enhancements', and speak closer to the mic.",
        ]
    elif peak >= CLIP_PEAK:
        lines.append("RESULT: the signal is clipping (too loud). Lower the Input volume or speak further away.")
    else:
        lines.append(f"RESULT: microphone level is fine (peak {dbfs(peak):.0f} dBFS).")
    if not have_model:
        lines.append("  - No speech model found, so recognition was not tested: python -m nova --download-model whisper-small")
    elif text:
        lines.append(f"  - The model heard: \"{text}\"")
        lines.append("  - If that differs from what you said it's an accuracy problem: use Whisper "
                     "(python -m nova --download-model whisper-small) or a bigger Whisper model.")
    else:
        lines.append("  - Sound arrived but the model recognised no words: speak clearly and nearer the mic; "
                     "Whisper (--download-model whisper-small) is far better than Vosk's small model.")
    return lines


def run_mic_test(
    device_name: str = "",
    seconds: float = 5.0,
    recognizer: Recognizer | None = None,
    source_factory: Callable[[], AudioSource] | None = None,
    out: Callable[[str], None] = print,
) -> int:
    devices = list(dict.fromkeys(list_input_devices())) if source_factory is None else []
    if devices:
        out("Input devices NOVA can see:")
        for d in devices:
            out(f"  - {d}")
    source = source_factory() if source_factory else MicCapture(device_name)
    stream = recognizer.new_stream() if recognizer else None
    try:
        source.start()
    except MicError as e:
        out(f"\nFAILED to open the microphone: {e}")
        return 1
    label = getattr(source, "device_label", "")
    out(f"\nUsing: {label or 'system default input'}")
    out(f"Speak now for {seconds:.0f} seconds - say, e.g., \"open notepad\"...\n")

    peak = 0
    text = ""
    window_peak = 0
    next_print = time.monotonic() + 0.4
    end = time.monotonic() + seconds
    try:
        while time.monotonic() < end:
            chunk = source.read(0.1)
            if chunk is None:
                continue
            p = max((abs(s) for s in array.array("h", chunk)), default=0)
            peak, window_peak = max(peak, p), max(window_peak, p)
            if stream is not None:
                text = stream.feed(chunk) or text
            if time.monotonic() >= next_print:
                out(f"  [{level_bar(window_peak)}] {dbfs(window_peak):5.0f} dB   {text}")
                window_peak, next_print = 0, time.monotonic() + 0.4
    finally:
        source.stop()
    if stream is not None:
        out("Recognising...")
        try:
            text = stream.finish() or text
        except SpeechError:
            pass
    out("")
    for line in verdict(peak, text, have_model=stream is not None):
        out(line)
    return 0
