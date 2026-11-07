#!/usr/bin/env python
"""Snapshots the real sandbox pages (agent-core's sites, rendered in-process) as static HTML fixtures, so the
extension's zone selectors are tested against the markup the sites actually serve.

    uv run python extension/scripts/snapshot_sandbox.py
"""
from __future__ import annotations

import re
from pathlib import Path

from starlette.testclient import TestClient

from understudy_agent.sandbox_sites import households as H
from understudy_agent.sandbox_sites import sites as SS
from understudy_agent.sandbox_sites import specs as S

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "sandbox"


def form_for(site: str, layout: str, h: H.Household) -> dict[str, str]:
    spec = S.SITES[site]
    params = h.params()
    keys = spec.fields(layout)
    return {keys[p]: S.bound_value(spec, p, params) for p in keys}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    h = next(x for x in H.generate_households(20, 2026) if x.archetype == "lone_parent_childcare")
    apps = SS.make_apps(SS.SandboxState(), {"a": 7801, "b": 7802, "c": 7803})
    for layout in ("v1", "v2"):
        q = "" if layout == "v1" else "?layout=v2"
        a, b, c = (TestClient(apps[s]) for s in "abc")
        fa, fb, fc = (form_for(s, layout, h) for s in "abc")
        pages = {
            f"a-step1-{layout}": a.get(f"/step/1{q}").text,
            f"a-step2-{layout}": a.post(f"/step/2{q}", data=fa).text,
            f"a-result-{layout}": a.post(f"/result{q}", data=fa).text,
            f"b-form-{layout}": b.get(f"/{q}").text,
            f"b-result-{layout}": b.post(f"/calculate{q}", data=fb).text,
            f"c-form-{layout}": c.get(f"/{q}").text,
            f"c-result-{layout}": c.post(f"/results{q}", data=fc).text,
            f"a-casenote-{layout}": a.get(f"/casenote{q}{'&' if q else '?'}case={h.case_ref}").text,
        }
        draft = a.post(f"/casenote/draft{q}", data={"case_ref": h.case_ref, "result_a": "1", "result_b": "2", "result_c": "3",
                                                    "reconciliation": "discrepancy", "note_text": "x"}, follow_redirects=True)
        pages[f"a-notedraft-{layout}"] = draft.text
        for name, html in pages.items():
            html = re.sub(r"http://127\.0\.0\.1:\d+", "http://127.0.0.1:7801", html)
            (OUT / f"{name}.html").write_text(html, encoding="utf-8")
    print("wrote", len(list(OUT.glob("*.html"))), "pages to", OUT)


if __name__ == "__main__":
    main()
