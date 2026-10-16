"""Download a speech model (Whisper via the Hugging Face hub, Vosk from alphacephei.com). Run on the Lenovo:

    python -m nova --download-model whisper-small     (recommended)
    python -m nova --download-model vosk-small        (weaker, smaller)
"""

from __future__ import annotations

import shutil
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from .. import paths

BASE_URL = "https://alphacephei.com/vosk/models/"
MODELS = {
    # key: (folder name, approx. download size)
    "small": ("vosk-model-small-en-us-0.15", "40 MB"),
    "large": ("vosk-model-en-us-0.22-lgraph", "128 MB"),
}


WHISPER_SIZES = {"base": "base.en", "small": "small.en"}  # ~140 MB / ~480 MB


class DownloadError(Exception):
    pass


def download_whisper(key: str, progress: Callable[[str], None] = print) -> Path:
    """key: 'base' or 'small'. Fetched from the Hugging Face hub by faster-whisper."""
    if key not in WHISPER_SIZES:
        raise DownloadError(f"Unknown Whisper model '{key}'. Choose: {', '.join(WHISPER_SIZES)}")
    size = WHISPER_SIZES[key]
    final = paths.models_dir() / f"whisper-{size}"
    if (final / "model.bin").is_file():
        progress(f"Already installed: {final}")
        return final
    try:
        from faster_whisper.utils import download_model as fw_download
    except ImportError as e:
        raise DownloadError("faster-whisper isn't installed. Run: pip install -r requirements.txt") from e
    progress(f"Downloading Whisper {size} from the Hugging Face hub (this can take a few minutes)...")
    try:
        fw_download(size, output_dir=str(final))
    except Exception as e:
        shutil.rmtree(final, ignore_errors=True)
        raise DownloadError(f"Download failed: {e}. Check your internet connection and try again.") from e
    if not (final / "model.bin").is_file():
        shutil.rmtree(final, ignore_errors=True)
        raise DownloadError("The download finished but model.bin is missing.")
    progress(f"Installed to {final}")
    return final


def safe_extract(zip_path: Path, dest: Path) -> None:
    """Extract, refusing any entry that would land outside `dest` (zip-slip)."""
    dest = dest.resolve()
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            target = (dest / member).resolve()
            if target != dest and dest not in target.parents:
                raise DownloadError(f"Refusing unsafe path in archive: {member}")
        zf.extractall(dest)


def download_model(key: str = "small", progress: Callable[[str], None] = print) -> Path:
    """key: whisper-base | whisper-small | vosk-small | vosk-large (small/large = the Vosk ones)."""
    if key.startswith("whisper-"):
        return download_whisper(key.split("-", 1)[1], progress)
    key = key.removeprefix("vosk-")
    if key not in MODELS:
        raise DownloadError(f"Unknown model '{key}'. Choose: {', '.join(MODELS)}")
    name, size = MODELS[key]
    models = paths.models_dir()
    final = models / name
    if (final / "am").is_dir():
        progress(f"Already installed: {final}")
        return final

    url = f"{BASE_URL}{name}.zip"
    tmp_zip = models / f"{name}.zip.part"
    progress(f"Downloading {name} (~{size}) from {url}")
    try:
        with urllib.request.urlopen(url, timeout=30) as resp, open(tmp_zip, "wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            done, last_pct = 0, -1
            while chunk := resp.read(256 * 1024):
                out.write(chunk)
                done += len(chunk)
                if total and done * 100 // total != last_pct and (done * 100 // total) % 10 == 0:
                    last_pct = done * 100 // total
                    progress(f"  {last_pct}%")
        progress("Extracting…")
        safe_extract(tmp_zip, models)
    except (OSError, zipfile.BadZipFile) as e:
        shutil.rmtree(final, ignore_errors=True)  # don't leave a half-extracted model behind
        raise DownloadError(f"Download failed: {e}. Check your internet connection and try again.") from e
    finally:
        tmp_zip.unlink(missing_ok=True)
    if not (final / "am").is_dir():
        raise DownloadError("The archive didn't contain the expected model files.")
    progress(f"Installed to {final}")
    return final
