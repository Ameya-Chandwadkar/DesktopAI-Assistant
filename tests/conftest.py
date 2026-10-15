import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nova.actions.apps import AppResolver  # noqa: E402
from nova.actions.engine import ActionEngine  # noqa: E402
from nova.config import Settings  # noqa: E402
from nova.controller import Assistant  # noqa: E402
from nova.db import Database  # noqa: E402
from nova.nlu.parser import LocalParser  # noqa: E402


class FakeSystem:
    """Records what would have happened instead of touching the PC."""

    def __init__(self):
        self.opened_paths: list[str] = []
        self.launched: list[tuple[str, list[str]]] = []
        self.urls: list[str] = []
        self.fail_with: OSError | None = None

    def open_path(self, path):
        if self.fail_with:
            raise self.fail_with
        self.opened_paths.append(path)

    def launch(self, exe, args=()):
        if self.fail_with:
            raise self.fail_with
        self.launched.append((exe, list(args)))

    def open_url_default(self, url):
        if self.fail_with:
            raise self.fail_with
        self.urls.append(url)


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_DATA_DIR", str(tmp_path / "data"))


@pytest.fixture
def docs(tmp_path):
    """A small document tree to search."""
    root = tmp_path / "docs"
    (root / "work").mkdir(parents=True)
    for rel in ("resume.pdf", "work/resume_old.docx", "work/Project Plan.docx", "notes.txt", "run.bat", "~$resume.docx"):
        (root / rel).write_text("x")
    return root


@pytest.fixture
def settings(docs):
    return Settings(search_roots=[str(docs)])


@pytest.fixture
def system():
    return FakeSystem()


@pytest.fixture
def apps(settings):
    # No registry / PATH: only custom_apps resolve, so tests are machine-independent.
    return AppResolver(lambda: settings, registry=lambda exe: None, which=lambda exe: None, search_install_dirs=False)


@pytest.fixture
def engine(settings, system, apps):
    return ActionEngine(lambda: settings, system, apps)


@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "test.db")
    yield d
    d.close()


@pytest.fixture
def assistant(engine, apps, settings, db):
    parser = LocalParser(apps.known_names, lambda: settings.custom_sites)
    return Assistant(engine, parser, db, lambda: settings)
