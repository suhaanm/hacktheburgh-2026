"""PLG-1: manifest schema, validator, loader, flags, the RawItem rules and the item schemas."""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from understudy_engine import plugins
from understudy_engine.plugins import (FieldSpec, ItemSchema, ManifestError, PluginDisabled, RawItem, Source, SourceError, check_item,
                                       discover, get_schema, load_manifest, load_source, register_manifest, register_schema, strip_sensitive,
                                       validate_paths)
from understudy_engine.plugins import cli, loader
from understudy_engine.plugins.manifest import check_manifest

UTC = timezone.utc
BUNDLED = {"git", "ics", "jsoncal", "graph_outlook", "graph_teams", "shell_times"}

GOOD = {"id": "ics", "version": "0.1.0", "kind": "source", "description": "ICS calendar files, read only.", "permissions": ["read"],
        "egress": "local_only", "schema": "calendar_event.v1", "entry": "understudy_engine.plugins.ics:ICSSource"}


def test_bundled_manifests_validate_and_graph_is_off():
    results = validate_paths()
    assert {r.id for r in results} == BUNDLED and all(r.ok for r in results), [(r.id, r.problems) for r in results if not r.ok]
    enabled = {r.id: r.enabled for r in results}
    assert enabled["graph_outlook"] is False and enabled["graph_teams"] is False
    assert all(enabled[i] for i in ("ics", "jsoncal", "shell_times", "git"))


def test_validate_cli_exit_codes(capsys, tmp_path):
    assert cli.validate_command([], quiet=True) == 0
    bad = tmp_path / "plugin.yaml"
    bad.write_text(yaml.safe_dump({**GOOD, "permissions": ["read", "write"]}))
    assert cli.validate_command([str(bad)]) == 1
    out = capsys.readouterr().out
    assert "FAIL" in out and "valid" in out
    assert plugins.cli.main(["validate", "--quiet"]) == 0


@pytest.mark.parametrize("patch,needle", [
    ({"permissions": ["read", "write"]}, "permissions"),
    ({"permissions": ["write"]}, "permissions"),
    ({"permissions": []}, "permissions"),
    ({"egress": "cloud"}, "egress"),
    ({"kind": "plugin"}, "kind"),
    ({"id": "Bad Id"}, "id"),
    ({"version": "1"}, "version"),
    ({"entry": "no_colon_here"}, "entry"),
    ({"schema": "nonexistent.v9"}, "registered item schema"),
    ({"network": True, "default_enabled": True, "enable_flag": "UNDERSTUDY_GRAPH"}, "default_enabled"),
    ({"network": True, "default_enabled": False}, "enable_flag"),
    ({"requires_token": True, "default_enabled": True, "enable_flag": "UNDERSTUDY_GRAPH"}, "default_enabled"),
    ({"id": "jsoncal"}, "plugin_id"),                                          # id must match the class
    ({"entry": "understudy_engine.plugins.jsoncal:JSONCalendarSource"}, "plugin_id"),
    ({"entry": "understudy_engine.plugins.ics:NoSuchClass"}, "cannot load"),
    ({"entry": "no.such.module:Thing"}, "cannot load"),
    ({"entry": "understudy_engine.plugins.base:RawItem"}, "not a Source"),
    ({"unknown_key": 1}, "unknown_key"),
])
def test_invalid_manifests_are_rejected(patch, needle):
    problems = check_manifest({**copy.deepcopy(GOOD), **patch})
    assert problems and any(needle in p for p in problems), problems


def test_a_source_manifest_needs_a_schema():
    d = {k: v for k, v in GOOD.items() if k != "schema"}
    assert any("schema" in p for p in check_manifest(d))
    d["kind"] = "skill"
    assert not [p for p in check_manifest({**d, "entry": "understudy_engine.plugins.ics:ICSSource"}) if "schema" in p and "required" in p]


def test_load_manifest_path_and_errors(tmp_path):
    m = load_manifest(Path(loader.BUILTIN_DIR) / "ics")
    assert m.id == "ics" and m.permissions == ("read",) and m.egress == "local_only" and m.schema == "calendar_event.v1"
    f = tmp_path / "plugin.yaml"
    f.write_text("id: [unclosed")
    with pytest.raises(ManifestError):
        load_manifest(f)
    with pytest.raises(ManifestError) as e:
        load_manifest(tmp_path / "missing.yaml")
    assert "cannot read" in str(e.value)


class _Dummy(Source):
    plugin_id = "dummy"
    schema_id = "dummy_item.v1"

    def read(self, since=None, until=None):
        yield RawItem("dummy", datetime(2026, 11, 2, tzinfo=UTC), datetime(2026, 11, 2, tzinfo=UTC), {"note": "x"})


def test_another_track_can_register_its_own_schema_and_manifest(tmp_path):
    register_schema(ItemSchema("dummy_item.v1", "dummy", {"note": FieldSpec("note", "str", sensitive=True)}))
    import sys
    import types
    mod = types.ModuleType("dummy_plugin_mod")
    mod.DummySource = _Dummy
    sys.modules["dummy_plugin_mod"] = mod
    try:
        m = register_manifest({"id": "dummy", "version": "0.0.1", "kind": "source", "description": "A dummy source for tests.", "permissions": ["read"],
                               "egress": "local_only", "schema": "dummy_item.v1", "entry": "dummy_plugin_mod:DummySource"})
        assert m.id == "dummy" and "dummy" in discover()
        src = load_source("dummy")
        assert [i.kind for i in src.read()] == ["dummy"]
        assert any(r.id == "dummy" and r.ok for r in validate_paths())
        with pytest.raises(ManifestError):
            register_manifest({**{"id": "dummy2", "version": "0.0.1", "kind": "source", "description": "bad dummy", "permissions": ["write"],
                                  "egress": "local_only", "schema": "dummy_item.v1", "entry": "dummy_plugin_mod:DummySource"}})
    finally:
        loader.unregister("dummy")
        sys.modules.pop("dummy_plugin_mod", None)


def test_plugin_path_env_adds_manifests(tmp_path, monkeypatch):
    d = tmp_path / "extra" / "myics"
    d.mkdir(parents=True)
    (d / "plugin.yaml").write_text(yaml.safe_dump({**GOOD, "id": "ics"}))
    monkeypatch.setenv("UNDERSTUDY_PLUGIN_PATH", str(tmp_path / "extra"))
    assert any(str(d) in str(p) for p in loader.manifest_paths())


def test_graph_sources_are_off_until_the_flag_is_set(monkeypatch):
    with pytest.raises(PluginDisabled):
        load_source("graph_outlook", token_provider=lambda: "t")
    with pytest.raises(PluginDisabled):
        load_source("graph_teams", token_provider=lambda: "t")
    # even with the registry's check passed, a real transport is refused without the flag (tests inject a fake fetch instead)
    from understudy_engine.plugins.graph_outlook import OutlookGraphSource
    with pytest.raises(SourceError) as e:
        OutlookGraphSource(lambda: "t")
    assert e.value.code == "graph_disabled"
    with pytest.raises(SourceError):
        OutlookGraphSource(None, fetch=lambda u, h: {})                      # a token provider is required
    monkeypatch.setenv("UNDERSTUDY_GRAPH", "1")
    assert load_source("graph_outlook", token_provider=lambda: "t", fetch=lambda u, h: {"value": []}) is not None


def test_rawitem_rules():
    t = datetime(2026, 11, 2, 9, tzinfo=UTC)
    item = RawItem("calendar_event", t, t, {"title": "Confidential layoffs"})
    assert "layoffs" not in repr(item) and "layoffs" not in str(item) and "layoffs" not in f"{item!r}"
    with pytest.raises(ValueError):
        RawItem("x", datetime(2026, 11, 2, 9), t)                            # naive time refused
    with pytest.raises(ValueError):
        RawItem("x", t, datetime(2026, 11, 2, 8, tzinfo=UTC))                # ends before it starts
    assert RawItem("x", t, t).duration_s == 0
    from zoneinfo import ZoneInfo
    local = RawItem("x", datetime(2026, 7, 1, 9, tzinfo=ZoneInfo("Europe/London")), datetime(2026, 7, 1, 10, tzinfo=ZoneInfo("Europe/London")))
    assert local.t0.hour == 8 and local.t0.tzinfo == UTC                     # normalised to UTC


def test_item_schemas_check_and_strip():
    cal = get_schema("calendar_event.v1")
    assert {"title", "organizer", "attendees", "location", "series_id", "source_id"} <= cal.sensitive_fields
    ok = {"title": "t", "n_attendees": 3, "all_day": False, "show_as": "busy", "attendees": ["a@b.example"]}
    assert check_item(cal, "calendar_event", ok) == []
    errs = check_item(cal, "calendar_event", {"title": 3, "n_attendees": "3", "show_as": "weird", "bogus": 1, "attendees": "a"})
    assert len(errs) == 5 and not any("weird" in e or "bogus=1" in e for e in errs)           # described by field name, never by value
    assert check_item(cal, "commit", ok)                                                    # wrong kind
    assert strip_sensitive(cal, ok) == {"n_attendees": 3, "all_day": False, "show_as": "busy"}
    commit = get_schema("commit.v1")
    assert "tz_min" in commit.fields and commit.fields["tz_min"].type == "int" and not commit.fields["tz_min"].sensitive
    assert {"sha", "author", "message", "paths"} == set(commit.sensitive_fields)
    assert get_schema("shell_time.v1").sensitive_fields == frozenset()


def test_every_bundled_schema_field_is_typed():
    for sid in plugins.schema_ids():
        s = get_schema(sid)
        assert all(f.type in ("str", "int", "float", "bool", "enum", "list_str") for f in s.fields.values())
        assert all(f.enum for f in s.fields.values() if f.type == "enum")


def test_manifest_schema_file_is_valid_json_schema():
    from jsonschema import Draft202012Validator
    from understudy_engine.store.paths import schema_dir
    Draft202012Validator.check_schema(json.loads((schema_dir() / "plugin.schema.json").read_text()))
