"""RD (7 Nov 2026): every selector in the role packs' capture config is valid CSS in a real browser engine, and no real-tool site shares a host with
a private sandbox. A selector that throws would silently turn a zone off in the extension; the pack validator only counts brackets and quotes, so the
browser is the check. This says the selectors parse, not that they match the live tools: those are still untested against live sites."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

PACKS = Path(__file__).resolve().parents[4] / "packages" / "packs"
ROLES = ("programmer", "data-analyst")


def all_selectors(role: str) -> list[tuple[str, str]]:
    m = yaml.safe_load((PACKS / role / "mapping.yaml").read_text())
    out: list[tuple[str, str]] = []
    for site in m["capture_sites"]:
        out += [(f"{site['id']}/{e['zone']}", e["selector"]) for e in site["elements"]]
        for key in ("nav", "tab", "page"):
            out += [(f"{site['id']}/{key}:{r['zone']}", r["when"]) for r in site.get(key, [])]
        mk = site.get("markers") or {}
        out += [(f"{site['id']}/progress:{r['kind']}", r["when"]) for r in mk.get("progress", [])]
        if mk.get("task_end"):
            out.append((f"{site['id']}/task_end", mk["task_end"]["when"]))
    return out


@pytest.mark.parametrize("role", ROLES)
def test_every_capture_selector_parses_in_chromium(new_page, role):
    page = new_page()
    page.goto("about:blank")
    sels = all_selectors(role)
    assert len(sels) >= 20
    bad = []
    for label, sel in sels:
        res = page.evaluate("(s) => { try { document.querySelector(s); document.body.matches(s); return true; } catch (e) { return String(e); } }", sel)
        if res is not True:
            bad.append((label, sel, res))
    assert not bad, bad


@pytest.mark.parametrize("role", ROLES)
def test_no_new_site_matches_a_sandbox_page(role):
    """The new sites' hosts never include a private sandbox port, so a sandbox page keeps its own (tested) capture config."""
    m = yaml.safe_load((PACKS / role / "mapping.yaml").read_text())
    sandbox = {h for s in m["capture_sites"] if s["id"] == "roles_sandbox" for h in s["hosts"]}
    for s in m["capture_sites"]:
        if s["id"] != "roles_sandbox":
            assert not sandbox & set(s["hosts"]), s["id"]
