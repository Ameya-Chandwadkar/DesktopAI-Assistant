import pytest

from nova.actions.models import Action
from nova.actions.registry import ACTION_SPECS, validate
from nova.actions.web import UrlError, looks_like_domain, spoken_to_url_text, validate_url


def test_allowlist_has_no_shell_or_code_actions():
    assert set(ACTION_SPECS) == {"open_url", "open_youtube", "open_app", "search_files", "open_file"}


@pytest.mark.parametrize(
    "action",
    [
        Action("open_url", {"url": "https://example.com"}),
        Action("open_youtube", {}),
        Action("open_youtube", {"query": "cats"}),
        Action("open_app", {"name": "notepad"}),
        Action("search_files", {"query": "resume", "kind": "pdf", "open_if_single": True}),
        Action("open_file", {"path": "C:\\Users\\x\\a.pdf"}),
    ],
)
def test_valid(action):
    assert validate(action) is None


@pytest.mark.parametrize(
    "action",
    [
        Action("run_shell", {"cmd": "calc"}),  # not on the allowlist
        Action("exec", {"code": "print(1)"}),
        Action("open_app", {}),  # missing arg
        Action("open_app", {"name": "notepad", "args": "--evil"}),  # unexpected arg
        Action("open_app", {"name": "notepad && del *"}),  # shell metacharacters rejected
        Action("open_app", {"name": 5}),  # wrong type
        Action("open_app", {"name": "x" * 100}),  # too long
        Action("open_url", {"url": ""}),
        Action("open_url", {"url": "a\x00b"}),
        Action("search_files", {"query": "x", "kind": "exe"}),
        Action("search_files", {"query": "x", "open_if_single": "yes"}),
        Action("search_files", {"query": "x", "open_if_single": 1}),
    ],
)
def test_invalid(action):
    assert validate(action) is not None


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("example.com", "https://example.com"),
        ("http://example.com/a?b=1", "http://example.com/a?b=1"),
        ("https://sub.example.co.uk/path", "https://sub.example.co.uk/path"),
        ("localhost:8000", "https://localhost:8000"),
    ],
)
def test_url_ok(raw, expected):
    assert validate_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "", "javascript:alert(1)", "file:///C:/Windows/System32/cmd.exe", "ftp://example.com",
        "https://user:pw@example.com", "https://google.com@evil.com", "ms-settings:", "not a url",
        "https://nodot", "data:text/html,hi", "calc.exe:",
    ],
)
def test_url_rejected(raw):
    with pytest.raises(UrlError):
        validate_url(raw)


def test_spoken_urls():
    assert spoken_to_url_text("Google dot com slash maps") == "google.com/maps"
    assert looks_like_domain("github dot com")
    assert not looks_like_domain("my resume")
