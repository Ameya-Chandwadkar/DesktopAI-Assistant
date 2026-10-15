import pytest

from nova.actions.models import Action
from nova.nlu.parser import LocalParser, parse_selection, split_kind


@pytest.fixture
def parser():
    return LocalParser(lambda: {"notepad", "vs code", "file explorer", "chrome"}, lambda: {"uni portal": "https://portal.example.edu"})


@pytest.mark.parametrize(
    "text,expected",
    [
        ("open notepad", Action("open_app", {"name": "notepad"})),
        ("Hey Nova, please open Notepad.", Action("open_app", {"name": "notepad"})),
        ("launch VS Code", Action("open_app", {"name": "vs code"})),
        ("open file explorer", Action("open_app", {"name": "file explorer"})),
        ("notepad", Action("open_app", {"name": "notepad"})),
        ("open youtube", Action("open_youtube", {})),
        ("go to youtube", Action("open_youtube", {})),
        ("search youtube for lo-fi music", Action("open_youtube", {"query": "lo-fi music"})),
        ("play jazz piano on youtube", Action("open_youtube", {"query": "jazz piano"})),
        ("open youtube and search for python tutorial", Action("open_youtube", {"query": "python tutorial"})),
        ("open github", Action("open_url", {"url": "https://github.com"})),
        ("open github dot com", Action("open_url", {"url": "github.com"})),
        ("go to example.org", Action("open_url", {"url": "example.org"})),
        ("open https://example.com/a", Action("open_url", {"url": "https://example.com/a"})),
        ("open uni portal", Action("open_url", {"url": "https://portal.example.edu"})),
        ("find resume", Action("search_files", {"query": "resume", "open_if_single": False})),
        ("find resume pdf", Action("search_files", {"query": "resume", "open_if_single": False, "kind": "pdf"})),
        ("search for the file called project plan", Action("search_files", {"query": "project plan", "open_if_single": False})),
        ("open file project plan", Action("search_files", {"query": "project plan", "open_if_single": True})),
        ("open the word document budget", Action("search_files", {"query": "budget", "open_if_single": True, "kind": "word"})),
        ("open budget", Action("search_files", {"query": "budget", "open_if_single": True})),
    ],
)
def test_parses(parser, text, expected):
    assert parser.parse(text) == expected


@pytest.mark.parametrize("text", ["", "   ", "what is the weather", "go to the shops", "hello there"])
def test_unrecognised(parser, text):
    # "open <unknown>" falls back to a file search by design, so only non-open phrases are tested here.
    assert parser.parse(text) is None


def test_nav_verb_never_searches_files(parser):
    assert parser.parse("go to my resume") is None


def test_split_kind():
    assert split_kind("resume pdf") == ("resume", "pdf")
    assert split_kind("the word document budget") == ("budget", "word")
    assert split_kind("called project plan file") == ("project plan", None)


@pytest.mark.parametrize(
    "text,count,expected",
    [
        ("2", 3, 1), ("number two", 3, 1), ("the second one", 3, 1), ("first", 3, 0),
        ("open number 3", 3, 2), ("open the third one", 3, 2), ("last", 3, 2),
        ("number to", 3, 1), ("cancel", 3, "cancel"), ("never mind", 3, "cancel"),
        ("4", 3, None), ("0", 3, None), ("to", 3, None), ("open notepad", 3, None),
    ],
)
def test_parse_selection(text, count, expected):
    assert parse_selection(text, count) == expected
