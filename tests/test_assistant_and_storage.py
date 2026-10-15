import json

from nova.actions.models import Status
from nova.config import Settings, SettingsStore


def test_unknown_command(assistant):
    out = assistant.submit("what is the weather like")
    assert out.result.status is Status.UNKNOWN and out.action is None


def test_empty_input(assistant):
    assert assistant.submit("   ").result.status is Status.UNKNOWN


def test_ambiguity_then_voice_selection(assistant, system):
    out = assistant.submit("find re")
    assert out.result.status is Status.NEEDS_CHOICE
    names = [c.label for c in out.result.choices]
    out2 = assistant.submit("number two")
    assert out2.result.ok and system.opened_paths[0].endswith(names[1])
    assert assistant.pending_choices == ()


def test_click_selection(assistant, system):
    assistant.submit("find re")
    assert assistant.choose(0).result.ok and len(system.opened_paths) == 1


def test_cancel_selection(assistant, system):
    assistant.submit("find re")
    assert assistant.submit("never mind").result.ok
    assert assistant.pending_choices == () and not system.opened_paths


def test_new_command_replaces_pending_list(assistant, system):
    assistant.submit("find re")
    assistant.submit("open youtube")
    assert assistant.pending_choices == () and system.urls


def test_choose_out_of_range(assistant):
    assert assistant.choose(5).result.status is Status.INVALID


def test_history_recorded_and_clearable(assistant, db):
    assistant.submit("open youtube", source="voice")
    assistant.submit("gibberish words")
    rows = db.recent_history()
    assert [(r.source, r.action, r.status) for r in rows] == [("text", "-", "unknown"), ("voice", "open_youtube", "ok")]
    db.clear_history()
    assert db.recent_history() == []


def test_history_can_be_disabled(assistant, db, settings):
    settings.history_enabled = False
    assistant.submit("open youtube")
    assert db.recent_history() == []


def test_settings_roundtrip(db):
    store = SettingsStore(db)
    s = store.get()
    s.browser = "chrome"
    s.custom_sites = {"portal": "https://example.edu"}
    store.update(s)
    again = SettingsStore(db).get()
    assert again.browser == "chrome" and again.custom_sites == {"portal": "https://example.edu"}


def test_settings_from_dict_ignores_garbage():
    s = Settings.from_dict({"browser": "netscape", "always_on_top": "yes", "search_roots": "C:\\", "max_search_results": 9999, "custom_apps": [1], "bogus": 1})
    d = Settings()
    assert s.browser == "default" and s.always_on_top is True
    assert s.search_roots == [] and s.max_search_results == 25 and s.custom_apps == {}


def test_import_config_file(db, tmp_path):
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({"_comment": "x", "search_roots": ["D:\\Study"], "browser": "edge"}))
    s = SettingsStore(db).import_file(cfg)
    assert s.search_roots == ["D:\\Study"] and s.browser == "edge"
    assert SettingsStore(db).get().browser == "edge"  # persisted


def test_prefs_default(db):
    assert db.get_pref("missing", 42) == 42
