import array
import queue
import time

from nova.speech.mic import MicError
from nova.speech.ptt import PushToTalk
from nova.speech.vosk_backend import SAMPLE_RATE, SpeechError, find_model


def pcm(seconds: float, amplitude: int) -> list[bytes]:
    """0.1 s chunks of a constant-level signal."""
    n = int(SAMPLE_RATE * 0.1)
    chunk = array.array("h", [amplitude] * n).tobytes()
    return [chunk] * int(seconds * 10)


class FakeSource:
    def __init__(self, chunks, fail=None):
        self._q = queue.Queue()
        for c in chunks:
            self._q.put(c)
        self.fail, self.stopped = fail, 0

    def start(self):
        if self.fail:
            raise self.fail

    def read(self, timeout):
        try:
            return self._q.get(timeout=timeout)
        except queue.Empty:
            return None

    def stop(self):
        self.stopped += 1


class FakeStream:
    def __init__(self, final="open notepad"):
        self.fed, self.final = 0, final

    def feed(self, data):
        self.fed += 1
        return "open" if self.fed < 3 else "open notepad"

    def finish(self):
        return self.final


class FakeRecognizer:
    def __init__(self, final="open notepad", error=None):
        self.final, self.error = final, error

    def new_stream(self):
        if self.error:
            raise self.error
        return FakeStream(self.final)


def run_ptt(source, recognizer=None, hold=0.3):
    events = []
    ptt = PushToTalk(
        recognizer or FakeRecognizer(),
        lambda: source,
        on_listening=lambda: events.append(("listening",)),
        on_partial=lambda t: events.append(("partial", t)),
        on_final=lambda t: events.append(("final", t)),
        on_error=lambda m: events.append(("error", m)),
    )
    assert ptt.start()
    time.sleep(hold)
    ptt.stop()
    ptt._thread.join(timeout=5)
    assert not ptt.busy
    return events, source


def test_happy_path():
    events, src = run_ptt(FakeSource(pcm(1.0, 3000)))
    kinds = [e[0] for e in events]
    assert kinds[0] == "listening" and events[-1] == ("final", "open notepad")
    assert ("partial", "open notepad") in events
    assert src.stopped >= 1


def test_too_short_press():
    events, _ = run_ptt(FakeSource(pcm(0.1, 3000)), hold=0.01)
    assert events[-1][0] == "error" and "too short" in events[-1][1]


def test_silence_gives_actionable_message():
    events, _ = run_ptt(FakeSource(pcm(1.0, 0)), FakeRecognizer(final=""))
    assert events[-1][0] == "error" and "silence" in events[-1][1] and "Privacy" in events[-1][1]


def test_noise_but_no_words():
    events, _ = run_ptt(FakeSource(pcm(1.0, 4000)), FakeRecognizer(final=""))
    assert events[-1][0] == "error" and "make out" in events[-1][1]


def test_mic_error_reported():
    events, _ = run_ptt(FakeSource([], fail=MicError("No microphone was found.")))
    assert events == [("error", "No microphone was found.")]


def test_model_error_reported():
    events, _ = run_ptt(FakeSource([]), FakeRecognizer(error=SpeechError("model not loaded")))
    assert events == [("error", "model not loaded")]


def test_unexpected_exception_is_contained():
    events, _ = run_ptt(FakeSource([]), FakeRecognizer(error=RuntimeError("kaboom")))
    assert events[0][0] == "error" and "log file" in events[0][1]


def test_find_model(tmp_path, monkeypatch):
    assert find_model() is None  # empty data dir
    from nova import paths

    (paths.models_dir() / "vosk-model-small-en-us-0.15" / "am").mkdir(parents=True)
    (paths.models_dir() / "vosk-model-en-us-0.22-lgraph" / "am").mkdir(parents=True)
    (paths.models_dir() / "junk").mkdir()
    assert find_model().name == "vosk-model-en-us-0.22-lgraph"  # prefers the bigger model
    assert find_model(str(tmp_path / "nope")) is None
    assert find_model(str(tmp_path)) == tmp_path


# ---- mic test tool -----------------------------------------------------
def run_test(chunks, recognizer=None, fail=None):
    from nova.speech.mic_test import run_mic_test

    lines = []
    code = run_mic_test("", seconds=0.5, recognizer=recognizer, source_factory=lambda: FakeSource(chunks, fail=fail), out=lines.append)
    return code, "\n".join(lines)


def test_mic_test_silence_points_at_privacy():
    code, text = run_test(pcm(1.0, 0))
    assert code == 0 and "no sound reached NOVA" in text and "Privacy" in text


def test_mic_test_quiet_mic_advice():
    _, text = run_test(pcm(1.0, 500))
    assert "VERY QUIET" in text and "Input volume" in text


def test_mic_test_good_level_shows_heard_text():
    _, text = run_test(pcm(1.0, 8000), FakeRecognizer(final="open notepad"))
    assert "level is fine" in text and 'heard: "open notepad"' in text


def test_mic_test_no_model_says_so():
    _, text = run_test(pcm(1.0, 8000))
    assert "download-model" in text


def test_mic_test_clipping():
    _, text = run_test(pcm(1.0, 32700))
    assert "clipping" in text


def test_mic_test_open_failure():
    code, text = run_test([], fail=MicError("No microphone was found."))
    assert code == 1 and "FAILED" in text


def test_level_bar_bounds():
    from nova.speech.mic_test import level_bar

    assert level_bar(0) == "." * 24 and level_bar(32767) == "#" * 24
