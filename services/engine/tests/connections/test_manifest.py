"""The curated list: every manifest is valid and verified, the packs offer the right sets, a floating version or a shell is refused, the command
hash pins what would run, and the consent line names publisher, package, pinned version, hosts and "with your token"."""
from __future__ import annotations

import copy
from dataclasses import replace

import yaml
from understudy_engine.connections import registry
from understudy_engine.connections.manifest import LAUNCHERS, Preset, command_hash, connection_problems, consent, standin_script_sha
from understudy_engine.plugins.loader import presets_dir
from understudy_engine.plugins.manifest import check_manifest

DEV = {"github", "local_git", "jira", "slack", "sentry", "filesystem"}
DATA = {"sqlite", "postgres", "bigquery", "google_workspace", "jupyter", "notion", "slack"}
BENEFITS = {"graph_outlook", "graph_teams", "sharepoint"}


def _load(name: str) -> dict:
    return yaml.safe_load((presets_dir() / f"{name}.yaml").read_text(encoding="utf-8"))


def test_the_curated_list_has_no_problems():
    assert registry.problems() == []


def test_the_three_role_packs_offer_the_owners_sets():
    roles = registry.role_lists()
    assert set(roles["programmer"]) == DEV and set(roles["data-analyst"]) == DATA and set(roles["benefits-processor"]) == BENEFITS
    assert len(registry.all_presets()) == len(DEV | DATA | BENEFITS)


def test_nothing_is_on_by_default_and_every_shipped_real_mode_is_verified_with_sources():
    for p in registry.all_presets().values():
        assert p.real is not None and p.real["verified"] is True and p.real["verified_on"].startswith("2026-")
        assert len(p.real["sources"]) >= 2 and all(s.startswith("https://") for s in p.real["sources"])
        if p.kind == "mcp":
            m = _load(p.id)
            assert m["default_enabled"] is False and m["permissions"] == ["read"]


def test_only_pinned_exact_versions_and_known_launchers_without_a_shell():
    for p in registry.all_presets().values():
        r = p.real
        if r["transport"] != "stdio":
            continue
        assert r["command"] in LAUNCHERS and r["version"][0].isdigit()
        assert any(r["version"] in a for a in r["args"]), p.id
        for a in r["args"]:
            assert "latest" not in a and not any(c in a.replace("{", "").replace("}", "") for c in ";&|`$<>\\\n"), (p.id, a)
        if r["command"] == "npx":
            assert r["args"][0] == "-y"
        for env in p.credential_envs:
            assert env.isupper()


def test_tokens_are_named_never_valued_in_a_manifest():
    for p in registry.all_presets().values():
        for k in (p.real.get("env_fixed") or {}):
            assert not any(w in k for w in ("TOKEN", "SECRET", "PASSWORD", "KEY")), (p.id, k)


def test_a_floating_version_is_refused():
    m = _load("slack")
    m["connection"]["real"]["args"] = ["-y", "slack-mcp-server@latest", "--transport", "stdio"]
    probs = check_manifest(m)
    assert any("pinned version" in x or "floating" in x for x in probs)


def test_a_shell_character_or_unknown_placeholder_is_refused():
    m = _load("filesystem")
    m["connection"]["real"]["args"] = ["-y", "@modelcontextprotocol/server-filesystem@2.2.0", "--read-only", "/tmp; rm -rf /"]
    assert any("shell" in x for x in connection_problems(m))
    m = _load("filesystem")
    m["connection"]["real"]["args"] = ["-y", "@modelcontextprotocol/server-filesystem@2.2.0", "{nothing}"]
    assert any("not a declared param" in x for x in connection_problems(m))


def test_a_launcher_that_is_a_shell_or_a_bare_interpreter_is_refused():
    for bad in ("sh", "bash", "python", "node", "curl"):
        m = _load("filesystem")
        m["connection"]["real"]["command"] = bad
        assert check_manifest(m), bad


def test_a_docker_launch_must_pin_the_image_and_mount_nothing():
    m = _load("github")
    m["connection"]["real"]["args"] = ["run", "-i", "--rm", "-v", "/:/host", "ghcr.io/github/github-mcp-server:2.1.0"]
    assert any("docker launch" in x for x in connection_problems(m))
    m = _load("github")
    m["connection"]["real"]["args"] = ["run", "-i", "--rm", "ghcr.io/github/github-mcp-server:latest"]
    assert connection_problems(m)


def test_a_tool_in_two_classes_or_a_secret_looking_fixed_variable_is_refused():
    m = _load("slack")
    m["connection"]["tools"]["classes"]["destructive"].append("channels_list")
    assert any("both" in x for x in connection_problems(m))
    m = _load("slack")
    m["connection"]["real"]["env_fixed"]["SLACK_TOKEN_X"] = "abc"
    assert any("secret" in x for x in connection_problems(m))


def test_a_mcp_manifest_has_no_entry_and_needs_a_connection_block():
    m = _load("filesystem")
    m["entry"] = "os.path:join"
    assert any("no entry" in x for x in check_manifest(m))
    m = _load("filesystem")
    del m["connection"]
    assert check_manifest(m)


def test_an_unverified_real_mode_cannot_ship():
    m = _load("jira")
    m["connection"]["real"]["verified"] = False
    assert connection_problems(m)


def test_the_command_hash_is_stable_and_pins_what_would_run():
    p = registry.get("slack")
    h = command_hash(p, "real")
    assert h == command_hash(p, "real") and h.startswith("sha256:") and command_hash(p, "example") != h
    for change in ({"version": "1.3.1"}, {"args": [*p.real["args"], "--extra"]}, {"hosts": ["evil.example"]}, {"env_fixed": {"A_B_C": "1"}}):
        assert command_hash(replace(p, real={**p.real, **change}), "real") != h, change
    # a worker's own folder or address is an input, not code: it is not in the hash
    fs = registry.get("filesystem")
    assert command_hash(fs, "real") == command_hash(fs, "real")


def test_a_stand_in_script_change_changes_its_hash(monkeypatch, tmp_path):
    import understudy_engine.connections.manifest as mf

    p = registry.get("github")
    base = standin_script_sha(p)
    fake_root = tmp_path / "repo"
    (fake_root / "packages/connections/standins").mkdir(parents=True)
    (fake_root / "packages/connections/standins/x.py").write_text("print(1)")
    monkeypatch.setattr(mf, "repo_root", lambda: fake_root)
    first = standin_script_sha(p)
    (fake_root / "packages/connections/standins/x.py").write_text("print(2)")
    assert first != standin_script_sha(p) and first != base


def test_the_real_consent_names_publisher_package_version_hosts_and_with_your_token():
    for pid in ("slack", "github", "jira", "sentry", "notion"):
        p = registry.get(pid)
        text = consent(p, "real", {"site": "https://acme.example.org"})["summary"]
        assert p.real["publisher"].split(" (")[0] in text and p.real["package"] in text and p.real["version"] in text, pid
        assert "with your token" in text, pid
        assert any(h in text for h in p.hosts({"site": "https://acme.example.org"})), pid
        assert "Revoke any time" in text
    assert "acme.example.org" in consent(registry.get("jira"), "real", {"site": "https://acme.example.org"})["summary"]


def test_a_local_server_says_it_stays_on_this_mac_and_the_example_says_no_account():
    assert "stays on this Mac" in consent(registry.get("filesystem"), "real")["summary"]
    ex = consent(registry.get("github"), "example")
    assert ex["example"] is True and "No account is used" in ex["summary"] and ex["hosts"] == []


def test_the_chip_carries_the_honest_flags_on_notion_and_sentry_and_no_other_tag():
    assert sorted(p.id for p in registry.all_presets().values() if p.caution) == ["notion", "sentry"]
    assert registry.get("notion").caution == "Vendor says unmaintained"
    assert registry.get("sentry").caution == "Source-available licence"
    assert "Source-available licence" in consent(registry.get("sentry"), "real")["summary"]
    assert "FSL" in registry.get("sentry").real["license"]


def test_preset_view_is_immutable_data():
    p = registry.get("slack")
    assert isinstance(p, Preset) and p.tools.counts()["send"] == 1 and p.tools.lookup("conversations_add_message") == "send"
    d = copy.deepcopy(p.real)
    assert d == p.real


def test_a_kind_tool_manifest_needs_an_entry_that_is_a_callable_and_a_connection_block():
    m = _load("filesystem")
    m["kind"] = "tool"
    assert any("entry" in x or "required" in x for x in check_manifest(m)), "a tool without an entry is refused"
    m["entry"] = "understudy_engine.plugins.manifest:resolve_tool_entry"
    assert check_manifest(m) == []
    m["entry"] = "os.path:sep"
    assert any("not callable" in x for x in check_manifest(m))
    m["entry"] = "no_such_module_xyz:thing"
    assert any("cannot load" in x for x in check_manifest(m))
    del m["connection"]
    m["entry"] = "understudy_engine.plugins.manifest:resolve_tool_entry"
    assert check_manifest(m), "a tool without a connection block is refused"


def test_a_source_preset_keeps_its_source_rules_and_may_carry_a_connection_block():
    import yaml
    from understudy_engine.plugins.loader import BUILTIN_DIR

    m = yaml.safe_load((BUILTIN_DIR / "graph_outlook" / "plugin.yaml").read_text())
    assert m["kind"] == "source" and m["connection"]["real"]["transport"] == "plugin" and check_manifest(m) == []
    m["egress"] = "app_only"
    assert check_manifest(m), "a source can never be app_only: its raw items stay on this machine"
    m = yaml.safe_load((BUILTIN_DIR / "graph_outlook" / "plugin.yaml").read_text())
    m["connection"]["real"]["transport"] = "stdio"
    assert check_manifest(m), "a source preset cannot pretend to be a stdio server"
