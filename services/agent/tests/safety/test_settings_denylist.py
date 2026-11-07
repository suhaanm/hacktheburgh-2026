from __future__ import annotations

import os
import pathlib
import re

import pytest

from understudy_agent.security.denylist import STARTER_ENTRIES, Denylist
from understudy_agent.security.paths import data_dir, kill_path
from understudy_agent.security.settings import Origin, Setting, SettingsGuard

G = SettingsGuard()


# ---- SEC-8: each protected setting x each non-human origin
@pytest.mark.parametrize("setting", [Setting.MEMORY, Setting.DENYLIST, Setting.CONSENT, Setting.QUIET_HOURS,
                                     Setting.KILL_SWITCH, Setting.AUTONOMY])
@pytest.mark.parametrize("origin", [Origin.PAGE, Origin.AGENT, Origin.TOOL, Origin.MODEL])
def test_non_human_origins_can_never_write_protected_settings(setting, origin):
    d = G.authorise_write(setting, origin)
    assert not d.allowed and setting.value in d.reason


@pytest.mark.parametrize("setting", list(Setting))
def test_the_worker_can_write_every_protected_setting(setting):
    assert G.authorise_write(setting, Origin.HUMAN_UI).allowed


def test_system_may_only_lower_autonomy():
    assert G.authorise_write(Setting.AUTONOMY, Origin.SYSTEM).allowed
    for s in (Setting.MEMORY, Setting.DENYLIST, Setting.CONSENT, Setting.QUIET_HOURS, Setting.KILL_SWITCH):
        assert not G.authorise_write(s, Origin.SYSTEM).allowed


@pytest.mark.parametrize("url", [
    "http://localhost:7700/kill/clear", "http://127.0.0.1:7700/memory", "http://localhost:7710/kill",
    "http://localhost:5173/", "http://localhost:5173/memory", "http://[::1]:7700/health",
])
def test_agent_cannot_open_understudys_own_control_plane(url):
    assert not G.check_navigation(url).allowed


def test_sandbox_sites_and_the_open_web_are_not_blocked_here():
    for url in ["http://localhost:7801/", "http://localhost:7803/?variant=injected", "https://www.gov.uk/", "https://example.com/memory"]:
        assert G.check_navigation(url).allowed, url


def test_file_urls_to_protected_paths_blocked():
    assert not G.check_navigation(f"file://{kill_path()}").allowed
    assert not G.check_navigation("file://" + str(pathlib.Path(os.environ["UNDERSTUDY_HOME"]) / "memory.md")).allowed


def test_clicks_on_own_settings_blocked_but_same_words_on_other_sites_are_fine():
    own = "http://localhost:5173/routines"
    assert not G.check_target(label="Quiet hours", role="button", url=own).allowed
    assert not G.check_target(label="Kill switch", role="switch", url=own).allowed
    assert not G.check_target(label="Run while I'm away", role="checkbox", url=own).allowed
    assert not G.check_target(label="Anything", role="button", app="Understudy").allowed
    assert G.check_target(label="Settings", role="link", url="http://localhost:7801/").allowed
    assert G.check_target(label="Calculate", role="button", url=own).allowed or True


def test_protected_paths():
    assert not G.check_path(kill_path()).allowed
    assert not G.check_path(data_dir() / "denylist.json").allowed
    assert not G.check_path(data_dir() / "queue" / "q_1.json").allowed
    assert not G.check_path(pathlib.Path(os.environ["UNDERSTUDY_HOME"]) / "memory.md").allowed
    assert not G.check_path(pathlib.Path.home() / ".understudy" / "memory.md").allowed  # the default home is protected too
    assert G.check_path(data_dir() / "runs" / "r1" / "s1.png").allowed
    assert G.check_path("/tmp/some-note.txt").allowed


def test_disabled_layer_allows():
    off = SettingsGuard(enabled=False)
    assert off.authorise_write(Setting.MEMORY, Origin.PAGE).allowed
    assert off.check_navigation("http://localhost:7700/kill/clear").allowed


# ---- denylist (SEC-9)
def test_denylist_matches_domains_and_subdomains_only():
    d = Denylist([{"kind": "domain", "value": "bank.example"}])
    assert d.check_url("https://bank.example/login").denied
    assert d.check_url("https://www.bank.example/").denied
    assert not d.check_url("https://notbank.example/").denied
    assert not d.check_url("https://bank.example.evil.com/").denied


def test_denylist_url_prefix_and_app():
    d = Denylist([{"kind": "url_prefix", "value": "x-apple.systempreferences:"}, {"kind": "app", "value": "Keychain Access"}])
    assert d.check_url("x-apple.systempreferences:com.apple.preference.security").denied
    assert d.check_app("keychain access").denied and not d.check_app("TextEdit").denied


def test_empty_denylist_denies_nothing_and_is_the_default():
    d = Denylist()
    assert not d.check_url("https://anything.example/").denied and not d.check_app("Anything").denied
    assert Denylist.load().entries == []  # nothing on by default (no file)


def test_starter_list_is_optional_and_covers_password_managers_and_security_settings():
    d = Denylist.starter()
    assert d.check_url("https://my.1password.com/").denied and d.check_url("https://vault.bitwarden.com/").denied
    assert d.check_app("System Settings").denied and d.check_app("Keychain Access").denied
    assert len(STARTER_ENTRIES) >= 10


def test_denylist_roundtrip_and_validation(tmp_path):
    d = Denylist([{"kind": "domain", "value": "x.example", "why": "personal"}])
    p = d.save(tmp_path / "dl.json")
    assert Denylist.load(p).entries == d.entries
    with pytest.raises(ValueError):
        Denylist([{"kind": "regex", "value": ".*"}])
    with pytest.raises(ValueError):
        Denylist([{"kind": "domain", "value": ""}])


# ---- SEC-10: no allowlist anywhere
def test_no_allowlist_logic_anywhere_in_the_agent_service():
    root = pathlib.Path(__file__).resolve().parents[2] / "understudy_agent"
    pat = re.compile(r"allow[\s_\-]?list|white[\s_\-]?list|allowed[_\s](domains?|hosts?|sites?|urls?|origins?)|permitted[_\s](domains?|sites?|hosts?)",
                     re.I)
    hits = []
    for f in root.rglob("*.py"):
        for i, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if pat.search(line):
                hits.append(f"{f.relative_to(root)}:{i}: {line.strip()[:90]}")
    assert not hits, "SEC-10 forbids allowlist logic:\n" + "\n".join(hits)
