"""evals/report.facts.json: the headline counts of a report, so docs can quote them by key instead of typing them.

Everything here is read from the report just written (and a static count of test functions in the repository); nothing is typed in.
``flat`` repeats every scalar under a dotted key (``sections.ok``, ``limitations.high``, ``redteam.attacks``) for one-line lookups.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..store.paths import repo_root

PY_TEST = re.compile(r"^\s*(?:async\s+)?def\s+test_", re.MULTILINE)
TS_TEST = re.compile(r"^\s*(?:it|test)(?:\.\w+)*\(", re.MULTILINE)


def count_tests(root: Path | None = None) -> dict[str, Any]:
    """A static count of test functions per layer: Python ``def test_`` and TypeScript ``it(``/``test(``. Parametrised cases are not expanded, so
    the number is a floor on what a runner reports. Cheap and deterministic for a given tree."""
    root = root or repo_root()
    by_dir: dict[str, int] = {}

    def add(key: str, n: int) -> None:
        if n:
            by_dir[key] = by_dir.get(key, 0) + n

    for base, label in ((root / "services" / "engine" / "tests", "engine"), (root / "services" / "agent" / "tests", "agent")):
        if not base.is_dir():
            continue
        for f in sorted(base.rglob("test_*.py")):
            rel = f.relative_to(base).parts
            add(f"{label}/{rel[0] if len(rel) > 1 else '(top level)'}", len(PY_TEST.findall(f.read_text(encoding="utf-8", errors="ignore"))))
    for sub in ("evals/tests", "packages/packs/tests"):
        d = root / sub
        if d.is_dir():
            for f in sorted(d.rglob("test_*.py")):
                add(sub, len(PY_TEST.findall(f.read_text(encoding="utf-8", errors="ignore"))))
    for sub in ("apps/dashboard/src", "apps/desktop/src", "extension/src", "extension/test", "extension/tests"):
        d = root / sub
        if d.is_dir():
            for f in sorted(list(d.rglob("*.test.ts")) + list(d.rglob("*.test.tsx"))):
                if "node_modules" in f.parts:
                    continue
                add(sub, len(TS_TEST.findall(f.read_text(encoding="utf-8", errors="ignore"))))
    return {"counting": "static count of test functions (parametrised cases are not expanded, so a runner reports at least this many)",
            "by_dir": dict(sorted(by_dir.items())), "total": sum(by_dir.values())}


def _sec(report: dict[str, Any], name: str) -> dict[str, Any] | None:
    s = (report.get("sections") or {}).get(name)
    return s if isinstance(s, dict) and "status" not in s else None


def build_facts(report: dict[str, Any], *, root: Path | None = None, tests: bool = True) -> dict[str, Any]:
    secs = report.get("sections") or {}
    emap = report.get("evidence_map") or []
    by_status: dict[str, list[str]] = {}
    for e in emap:
        by_status.setdefault(e["status"], []).append(e["section"])
    lim = secs.get("limitations") or []
    facts: dict[str, Any] = {
        "generated_at": report.get("generated_at"), "mock": report.get("mock"), "git_rev": report.get("git_rev"),
        "fast": (report.get("run") or {}).get("fast"), "partial": len(emap) < 10,
        "note": "Read from evals/report.json by `make eval`. A fast run uses fewer resamples and seeds, so counts that depend on them differ from a full run; quote a full run.",
        "sections": {"total": len(emap), **{k: len(by_status.get(k, [])) for k in ("ok", "pending", "not_run", "failed", "invalid_provenance")},
                     **{f"{k}_names": by_status.get(k, []) for k in ("ok", "pending", "not_run", "failed", "invalid_provenance")}},
        "limitations": {"total": len(lim), **{sev: sum(1 for e in lim if e.get("severity") == sev) for sev in ("high", "medium", "low")}},
    }
    facts["findings"] = {"total": len(report.get("findings") or []), "ids": [f.get("id") for f in report.get("findings") or []],
                         "ok": [f.get("id") for f in report.get("findings") or [] if f.get("status") == "ok"]}
    rt = _sec(report, "redteam")
    if rt:
        rows = rt.get("rows") or []
        by = {r.get("ablation"): r for r in rows}
        facts["redteam"] = {"attacks": rows[0].get("n") if rows else None, "clean_cases": (rt.get("false_pause") or {}).get("n"), "configurations": len(rows),
                            "attack_success_all_on": (by.get("all_on") or {}).get("attack_success"), "attack_success_all_off": (by.get("all_off") or {}).get("attack_success"),
                            "false_pause_rate": rt.get("false_pause_rate")}
    rl = _sec(report, "redteam_live")
    if rl:
        on = next((r for r in rl.get("rows") or [] if r.get("ablation") == "all_on"), {})
        facts["redteam_live"] = {"cases": (rl.get("meta") or {}).get("n"), "repeats": rl.get("repeats"), "clean_pages": rl.get("n_clean"),
                                 "attack_runs_per_configuration": on.get("n_runs"), "attack_successes_all_on": on.get("attack_successes")}
    ar = _sec(report, "agent_runs")
    if ar:
        lv = ar.get("live") or {}
        facts["agent_runs"] = {"households": (ar.get("clean") or {}).get("n"), "clean_pass": (ar.get("clean") or {}).get("pass"), "robust_pass": (ar.get("robust") or {}).get("pass"),
                               "live_runs": lv.get("runs_total"), "live_headline_condition": lv.get("condition"), "live_headline_pass": lv.get("pass"),
                               "live_headline_n": lv.get("n"), "live_false_claims_by_condition": lv.get("false_claims_by_condition"),
                               "live_pass_by_condition": {k: v.get("pass") for k, v in (lv.get("pass_by_condition") or {}).items()},
                               "mock_false_claims": ar.get("false_claims")}
    pv = _sec(report, "privacy")
    if pv:
        h = pv.get("headline") or {}
        facts["privacy"] = {"flows": h.get("flows"), "runs": h.get("runs"), "planted_tokens": h.get("planted"), "leaked": h.get("leaked"),
                            "static_guard_violations": h.get("static_guard_violations"), "controls_passed": h.get("controls_passed"), "controls_total": h.get("controls_total")}
    elif isinstance(secs.get("privacy"), dict):
        facts["privacy"] = {"status": secs["privacy"].get("status"), "reason": secs["privacy"].get("reason")}
    st = secs.get("study")
    if isinstance(st, dict):
        facts["study"] = {"status": st.get("status", "ok"), "n": (st.get("meta") or {}).get("n"), "origin": (st.get("meta") or {}).get("origin")}
    if tests:
        facts["tests"] = count_tests(root)
    facts["flat"] = _flat({k: v for k, v in facts.items() if k not in ("flat", "note")})
    return facts


def _flat(o: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(o, dict):
        for k, v in o.items():
            out.update(_flat(v, f"{prefix}.{k}" if prefix else str(k)))
    elif not isinstance(o, list):
        out[prefix] = o
    return out
