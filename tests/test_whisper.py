import array
import sys
import types

import pytest

np = pytest.importorskip("numpy")

from nova import paths  # noqa: E402
from nova.config import Settings  # noqa: E402
from nova.speech import engines, model_download as md, whisper_backend as wb  # noqa: E402
from nova.speech.vosk_backend import SAMPLE_RATE, SpeechError  # noqa: E402


class FakeSegment:
    def __init__(self, text):
        self.text = text


class FakeWhisperModel:
    def __init__(self, texts=(" Open Notepad.",)):
        self.texts, self.calls = texts, []

    def transcribe(self, audio, **kwargs):
        self.calls.append((audio, kwargs))
        return iter([FakeSegment(t) for t in self.texts]), object()


def pcm_bytes(seconds, amplitude):
    return array.array("h", [amplitude] * int(SAMPLE_RATE * seconds)).tobytes()


def stream_with(model, data):
    rec = wb.WhisperRecognizer(paths.models_dir(), model_factory=lambda p: model)
    rec.load()
    s = rec.new_stream()
    for i in range(0, len(data), 6400):
        assert s.feed(data[i : i + 6400]) == ""  # never any live partials
    return s


def test_transcribes_with_command_settings():
    model = FakeWhisperModel((" Open", " Notepad."))
    text = stream_with(model, pcm_bytes(1.0, 9000)).finish()
    assert text == "Open Notepad."
    audio, kw = model.calls[0]
    assert audio.dtype == np.float32 and len(audio) == SAMPLE_RATE
    assert kw["language"] == "en" and kw["vad_filter"] is True and "Notepad" in kw["initial_prompt"]
    assert kw["condition_on_previous_text"] is False


def test_silence_never_reaches_whisper():
    model = FakeWhisperModel()
    assert stream_with(model, pcm_bytes(1.0, 0)).finish() == ""
    assert model.calls == []  # avoids hallucinated "thank you" on silence


def test_too_short_is_ignored():
    model = FakeWhisperModel()
    assert stream_with(model, pcm_bytes(0.1, 9000)).finish() == "" and model.calls == []


def test_quiet_mic_is_boosted_but_capped():
    model = FakeWhisperModel()
    stream_with(model, pcm_bytes(1.0, 1000)).finish()
    assert 0.25 < float(np.abs(model.calls[0][0]).max()) < 0.4  # 1000/32768 * 10 (the cap)
    loud = FakeWhisperModel()
    stream_with(loud, pcm_bytes(1.0, 12000)).finish()
    assert abs(float(np.abs(loud.calls[0][0]).max()) - 12000 / 32768) < 1e-4  # untouched


def test_recording_is_capped_at_30_seconds():
    s = stream_with(FakeWhisperModel(), b"")
    s.feed(b"\x01\x00" * (SAMPLE_RATE * 60))
    s.feed(b"\x01\x00" * 1000)
    assert len(s._buf) <= wb._MAX_BYTES + 2 * SAMPLE_RATE * 60  # stops growing once the cap is hit
    before = len(s._buf)
    s.feed(b"\x01\x00" * 1000)
    assert len(s._buf) == before


def test_stream_before_load_and_load_failure():
    with pytest.raises(SpeechError):
        wb.WhisperRecognizer(paths.models_dir()).new_stream()

    def boom(p):
        raise RuntimeError("corrupt model")

    with pytest.raises(SpeechError, match="download is complete|complete"):
        wb.WhisperRecognizer(paths.models_dir(), model_factory=boom).load()


# ---- engine selection ---------------------------------------------------
def make_whisper(name):
    d = paths.models_dir() / name
    d.mkdir(parents=True)
    (d / "model.bin").write_text("x")
    return d


def make_vosk(name="vosk-model-small-en-us-0.15"):
    d = paths.models_dir() / name
    (d / "am").mkdir(parents=True)
    return d


@pytest.fixture
def whisper_installed(monkeypatch):
    monkeypatch.setattr(engines, "whisper_available", lambda: True)


def test_find_whisper_prefers_small():
    make_whisper("whisper-base.en")
    make_whisper("whisper-small.en")
    assert wb.find_whisper_model().name == "whisper-small.en"


def test_whisper_dir_without_model_bin_ignored():
    (paths.models_dir() / "whisper-small.en").mkdir()
    assert wb.find_whisper_model() is None


def test_auto_prefers_whisper_then_falls_back(whisper_installed):
    make_vosk()
    assert engines.choose_engine(Settings()).kind == "vosk"
    make_whisper("whisper-small.en")
    assert engines.choose_engine(Settings()).kind == "whisper"


def test_forced_engines(whisper_installed):
    make_vosk()
    make_whisper("whisper-base.en")
    assert engines.choose_engine(Settings(speech_engine="vosk")).kind == "vosk"
    assert engines.choose_engine(Settings(speech_engine="whisper")).kind == "whisper"


def test_forced_whisper_without_model_does_not_silently_use_vosk(whisper_installed):
    make_vosk()
    assert engines.choose_engine(Settings(speech_engine="whisper")) is None


def test_whisper_package_missing_falls_back_to_vosk(monkeypatch):
    monkeypatch.setattr(engines, "whisper_available", lambda: False)
    make_vosk()
    make_whisper("whisper-small.en")
    assert engines.choose_engine(Settings()).kind == "vosk"


def test_no_models_at_all(whisper_installed):
    assert engines.choose_engine(Settings()) is None
    assert "whisper-small" in engines.missing_message(Settings())


def test_speech_engine_setting_validated():
    assert Settings.from_dict({"speech_engine": "vosk"}).speech_engine == "vosk"
    assert Settings.from_dict({"speech_engine": "banana"}).speech_engine == "auto"


# ---- downloading --------------------------------------------------------
def fake_fw_utils(monkeypatch, behaviour):
    mod = types.ModuleType("faster_whisper.utils")
    mod.download_model = behaviour
    monkeypatch.setitem(sys.modules, "faster_whisper.utils", mod)


def test_download_whisper_ok(monkeypatch):
    def fake(size, output_dir):
        assert size == "small.en"
        (paths.models_dir() / "whisper-small.en").mkdir(exist_ok=True)
        (paths.models_dir() / "whisper-small.en" / "model.bin").write_text("x")

    fake_fw_utils(monkeypatch, fake)
    out = md.download_model("whisper-small", progress=lambda m: None)
    assert out.name == "whisper-small.en"
    msgs = []
    md.download_model("whisper-small", progress=msgs.append)  # second call must not download again
    assert msgs == [f"Already installed: {out}"]


def test_download_whisper_failure_cleans_up(monkeypatch):
    def fake(size, output_dir):
        (paths.models_dir() / "whisper-base.en").mkdir()
        raise OSError("network down")

    fake_fw_utils(monkeypatch, fake)
    with pytest.raises(md.DownloadError, match="internet"):
        md.download_model("whisper-base", progress=lambda m: None)
    assert not (paths.models_dir() / "whisper-base.en").exists()


def test_download_unknown_whisper_size():
    with pytest.raises(md.DownloadError):
        md.download_model("whisper-gigantic")
