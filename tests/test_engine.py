from pathlib import Path

import pytest

from nova.actions.apps import AppResolver
from nova.actions.engine import ActionEngine
from nova.actions.models import Action, Status
from nova.config import Settings
from nova.files.safety import PathNotAllowed, resolve_allowed
from nova.files.search import search_files


# ---- web ---------------------------------------------------------------
def test_open_url_default_browser(engine, system):
    r = engine.execute(Action("open_url", {"url": "example.com"}))
    assert r.ok and system.urls == ["https://example.com"]


def test_open_url_rejects_dangerous_scheme(engine, system):
    r = engine.execute(Action("open_url", {"url": "file:///C:/Windows/System32/cmd.exe"}))
    assert r.status is Status.INVALID and not system.urls and not system.launched


def test_youtube_search_is_url_encoded(engine, system):
    engine.execute(Action("open_youtube", {"query": "lo-fi & chill/beats"}))
    assert system.urls == ["https://www.youtube.com/results?search_query=lo-fi+%26+chill%2Fbeats"]


def test_preferred_browser_used_when_found(system, settings):
    settings.browser = "chrome"
    resolver = AppResolver(lambda: settings, registry=lambda exe: "C:\\chrome.exe", which=lambda e: None, search_install_dirs=False)
    eng = ActionEngine(lambda: settings, system, resolver)
    assert eng.execute(Action("open_youtube", {})).ok
    assert system.launched == [("C:\\chrome.exe", ["https://www.youtube.com"])]


def test_preferred_browser_missing_falls_back_with_note(engine, system, settings):
    settings.browser = "chrome"
    r = engine.execute(Action("open_youtube", {}))
    assert r.ok and "default browser" in r.message and system.urls == ["https://www.youtube.com"]


def test_browser_failure_reported(engine, system):
    system.fail_with = OSError("boom")
    assert engine.execute(Action("open_youtube", {})).status is Status.ERROR


# ---- apps --------------------------------------------------------------
def test_unknown_app(engine):
    r = engine.execute(Action("open_app", {"name": "frobnicator"}))
    assert r.status is Status.NOT_FOUND and "Settings" in r.message


def test_known_app_not_installed(engine, system):
    r = engine.execute(Action("open_app", {"name": "vs code"}))
    assert r.status is Status.NOT_FOUND and "installed" in r.message and not system.launched


def test_installed_app_launches(system, settings):
    resolver = AppResolver(lambda: settings, registry=lambda exe: "C:\\Windows\\notepad.exe" if exe == "notepad.exe" else None, which=lambda e: None, search_install_dirs=False)
    eng = ActionEngine(lambda: settings, system, resolver)
    assert eng.execute(Action("open_app", {"name": "Notepad"})).ok
    assert system.launched == [("C:\\Windows\\notepad.exe", [])]


def test_custom_app(system, settings, tmp_path):
    exe = tmp_path / "mytool.exe"
    exe.write_text("")
    settings.custom_apps = {"my tool": str(exe)}
    eng = ActionEngine(lambda: settings, system, AppResolver(lambda: settings, lambda e: None, lambda e: None, search_install_dirs=False))
    assert eng.execute(Action("open_app", {"name": "my tool"})).ok
    assert system.launched == [(str(exe), [])]


def test_custom_app_with_missing_exe(system, settings):
    settings.custom_apps = {"ghost": "C:\\nope\\ghost.exe"}
    eng = ActionEngine(lambda: settings, system, AppResolver(lambda: settings, lambda e: None, lambda e: None, search_install_dirs=False))
    assert eng.execute(Action("open_app", {"name": "ghost"})).status is Status.NOT_FOUND


def test_launch_oserror(system, settings):
    resolver = AppResolver(lambda: settings, registry=lambda e: "C:\\x.exe", which=lambda e: None, search_install_dirs=False)
    system.fail_with = OSError("denied")
    r = ActionEngine(lambda: settings, system, resolver).execute(Action("open_app", {"name": "notepad"}))
    assert r.status is Status.ERROR


# ---- file search -------------------------------------------------------
def test_search_ranks_exact_first_and_skips_junk(docs):
    out = search_files("resume", [str(docs)])
    names = [h.path.name for h in out.hits]
    assert names == ["resume.pdf", "resume_old.docx"]  # no ~$ lock file, no .bat


def test_search_partial_and_multiword_case_insensitive(docs):
    assert [h.path.name for h in search_files("PLAN project", [str(docs)]).hits] == ["Project Plan.docx"]
    assert [h.path.name for h in search_files("not", [str(docs)]).hits] == ["notes.txt"]


def test_search_never_returns_executables(docs):
    assert search_files("run", [str(docs)]).hits == []


def test_search_missing_root_reported(docs, tmp_path):
    out = search_files("resume", [str(tmp_path / "nope"), str(docs)])
    assert out.missing_roots and out.hits


def test_search_skips_symlinked_dirs(docs, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.pdf").write_text("x")
    try:
        (docs / "link").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks need privileges on this Windows account")
    assert search_files("secret", [str(docs)]).hits == []


def test_engine_single_exact_match_opens_directly(engine, system):
    r = engine.execute(Action("search_files", {"query": "resume", "open_if_single": True}))
    assert r.ok and Path(system.opened_paths[0]).name == "resume.pdf"


def test_engine_ambiguous_returns_choices(engine, system):
    r = engine.execute(Action("search_files", {"query": "resume", "kind": "word", "open_if_single": True}))
    assert r.ok  # only one .docx matches "resume" -> opened
    system.opened_paths.clear()
    r = engine.execute(Action("search_files", {"query": "re", "open_if_single": True}))
    assert r.status is Status.NEEDS_CHOICE and len(r.choices) >= 2 and not system.opened_paths


def test_engine_find_lists_even_single_hit(engine, system):
    r = engine.execute(Action("search_files", {"query": "notes"}))
    assert r.status is Status.NEEDS_CHOICE and len(r.choices) == 1 and not system.opened_paths


def test_engine_no_match(engine):
    assert engine.execute(Action("search_files", {"query": "zzzz"})).status is Status.NOT_FOUND


def test_engine_no_roots_configured(system):
    s = Settings(search_roots=[])
    r = ActionEngine(lambda: s, system).execute(Action("search_files", {"query": "x"}))
    assert r.status is Status.NOT_FOUND and "Settings" in r.message


def test_engine_all_roots_missing(system, tmp_path):
    s = Settings(search_roots=[str(tmp_path / "gone")])
    r = ActionEngine(lambda: s, system).execute(Action("search_files", {"query": "x"}))
    assert r.status is Status.NOT_FOUND and "exist" in r.message


# ---- opening files / path safety --------------------------------------
def test_open_file_ok(engine, system, docs):
    assert engine.execute(Action("open_file", {"path": str(docs / "notes.txt")})).ok
    assert system.opened_paths == [str((docs / "notes.txt").resolve())]


def test_open_file_deleted_since_search(engine, docs):
    r = engine.execute(Action("open_file", {"path": str(docs / "ghost.pdf")}))
    assert r.status is Status.NOT_FOUND


def test_open_file_outside_roots_refused(engine, system, tmp_path):
    outside = tmp_path / "elsewhere.pdf"
    outside.write_text("x")
    assert engine.execute(Action("open_file", {"path": str(outside)})).status is Status.INVALID
    assert not system.opened_paths


def test_open_file_traversal_refused(engine, docs, tmp_path):
    outside = tmp_path / "elsewhere.pdf"
    outside.write_text("x")
    sneaky = str(docs / ".." / "elsewhere.pdf")
    assert engine.execute(Action("open_file", {"path": sneaky})).status is Status.INVALID


def test_open_file_executable_refused(engine, system, docs):
    assert engine.execute(Action("open_file", {"path": str(docs / "run.bat")})).status is Status.INVALID
    assert not system.opened_paths


def test_open_file_no_associated_app(engine, system, docs):
    system.fail_with = OSError("No application is associated with the specified file")
    r = engine.execute(Action("open_file", {"path": str(docs / "notes.txt")}))
    assert r.status is Status.ERROR and "associated" in r.message


def test_resolve_allowed_rejects_directory(docs):
    (docs / "folder.pdf").mkdir()
    with pytest.raises(PathNotAllowed):
        resolve_allowed(str(docs / "folder.pdf"), [str(docs)])


# ---- engine guard rails -----------------------------------------------
def test_engine_rejects_unlisted_action(engine):
    assert engine.execute(Action("run_shell", {"cmd": "calc"})).status is Status.INVALID


def test_confirmation_gate(engine, monkeypatch):
    from nova.actions import registry

    spec = registry.ACTION_SPECS["open_youtube"]
    monkeypatch.setitem(registry.ACTION_SPECS, "open_youtube", type(spec)(spec.name, spec.description, spec.args, requires_confirmation=True))
    assert engine.execute(Action("open_youtube", {})).status is Status.NEEDS_CONFIRMATION
    assert engine.execute(Action("open_youtube", {}), confirmed=True).ok


def test_handler_crash_is_contained(engine, monkeypatch):
    monkeypatch.setattr(engine, "_do_open_youtube", lambda **kw: 1 / 0)
    assert engine.execute(Action("open_youtube", {})).status is Status.ERROR
