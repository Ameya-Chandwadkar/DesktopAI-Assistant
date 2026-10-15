import zipfile

import pytest

from nova.speech import model_download as md


def make_zip(path, names):
    with zipfile.ZipFile(path, "w") as zf:
        for n in names:
            zf.writestr(n, "x")


def test_safe_extract_ok(tmp_path):
    z = tmp_path / "m.zip"
    make_zip(z, ["model/am/final.mdl", "model/conf/model.conf"])
    out = tmp_path / "out"
    out.mkdir()
    md.safe_extract(z, out)
    assert (out / "model" / "am" / "final.mdl").is_file()


@pytest.mark.parametrize("evil", ["../evil.txt", "model/../../evil.txt", "..\\evil.txt"])
def test_zip_slip_refused(tmp_path, evil):
    z = tmp_path / "m.zip"
    make_zip(z, ["model/am/x", evil])
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(md.DownloadError):
        md.safe_extract(z, out)
    assert not (tmp_path / "evil.txt").exists()


def test_unknown_model_key():
    with pytest.raises(md.DownloadError):
        md.download_model("huge")


def test_already_installed_skips_download(monkeypatch):
    from nova import paths

    (paths.models_dir() / md.MODELS["small"][0] / "am").mkdir(parents=True)
    monkeypatch.setattr(md.urllib.request, "urlopen", lambda *a, **k: pytest.fail("should not download"))
    msgs = []
    md.download_model("small", progress=msgs.append)
    assert "Already installed" in msgs[0]


def test_network_failure_is_reported(monkeypatch):
    def boom(*a, **k):
        raise OSError("no network")

    monkeypatch.setattr(md.urllib.request, "urlopen", boom)
    with pytest.raises(md.DownloadError, match="internet"):
        md.download_model("small", progress=lambda m: None)
