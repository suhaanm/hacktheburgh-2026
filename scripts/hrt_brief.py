#!/usr/bin/env python3
"""Render docs/HRT_BRIEF.md from docs/hrt/HRT_BRIEF.tmpl.md, filling every number from the reports under evals/.

No number in the brief is typed by hand. A placeholder is ``{{src:path/to/value|fmt}}``:

  src   one of  r (evals/report.json, from its ``sections``)  rt (evals/report.json, top level)  hl (evals/hrt/results/heldout_ledger.json)
        hd (evals/hrt/results/heldout_decisions.json)  hr (evals/hrt/results/heldout_recal.json)  hc (evals/hrt/results/heldout_conformal.json)
        mh (evals/mlv2/results/heldout_hazard.json)  mm (evals/mlv2/results/heldout_mismatch.json)  cue (evals/cue/held_out.json)
        hm (computed here, not read: the Holm family over the reported intervals; ``hm:m``, ``hm:survivors``, ``hm:table``, ``hm:note``)
  path  keys and list indexes separated by "/"; ``id=P1`` picks the list item whose ``id`` is P1; ``1:3`` is not supported (name the index)
  assert  ``<!-- assert src:path < src:path -->`` (or > , or a number on either side) is checked at render time: a sentence in the template that says "beats" or
        "loses" carries the inequality that makes it true, and the render fails if a report ever contradicts it
  fmt   f1..f4 (decimals)  s3 (signed, 3 decimals)  p0 p1 p2 (a share as a percentage)  i (integer with separators)  ci2 ci3 ci4 (an interval)
        pci1 pci0 (an interval of shares as percentages)  word (underscores to spaces)  yn (yes or no)  held (passed or did not pass)  raw (as is)

Usage:  python3 scripts/hrt_brief.py            write docs/HRT_BRIEF.md
        python3 scripts/hrt_brief.py --check    exit 1 if the committed brief differs from a fresh render (a report changed: re-run without --check)
Run it again after `make eval` or after any file under evals/hrt/results or evals/mlv2/results changes.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "docs" / "hrt" / "HRT_BRIEF.tmpl.md"
OUT = ROOT / "docs" / "HRT_BRIEF.md"
SOURCES = {
    "r": (ROOT / "evals" / "report.json", "sections"),
    "rt": (ROOT / "evals" / "report.json", None),
    "hl": (ROOT / "evals" / "hrt" / "results" / "heldout_ledger.json", None),
    "hd": (ROOT / "evals" / "hrt" / "results" / "heldout_decisions.json", None),
    "hr": (ROOT / "evals" / "hrt" / "results" / "heldout_recal.json", None),
    "hc": (ROOT / "evals" / "hrt" / "results" / "heldout_conformal.json", None),
    "mh": (ROOT / "evals" / "mlv2" / "results" / "heldout_hazard.json", None),
    "mm": (ROOT / "evals" / "mlv2" / "results" / "heldout_mismatch.json", None),
    "cue": (ROOT / "evals" / "cue" / "held_out.json", None),
}
ASSERT = re.compile(r"<!--\s*assert\s+(\S+)\s*([<>])\s*(\S+?)\s*-->")
PLACEHOLDER = re.compile(r"\{\{\s*([a-z]+):([^|}]+?)\s*(?:\|\s*([a-z0-9]+))?\s*\}\}")
_cache: dict[str, Any] = {}


class Unresolved(KeyError):
    pass


# ----------------------------------------------------------------------------------------- family size and Holm-adjusted p-values
Z95 = 1.959963984540054
# the family: every registered directional paired contrast that has a reported 95% interval (est path, interval path); claims that are "an interval contains the
# nominal level" or "at least 2 of 3" rules are not hypothesis tests and are counted in the registered-claims total but not here
HOLM_ROWS = (
    ("P1a", "v1 world: stuck model minus online base rate (log loss)", "hl", "claims/id=P1/evidence/online_base/est", "claims/id=P1/evidence/online_base/ci"),
    ("P1b", "v1 world: stuck model minus frozen time since progress (log loss)", "hl", "claims/id=P1/evidence/frozen_tsp/est", "claims/id=P1/evidence/frozen_tsp/ci"),
    ("P3-markov", "markov world: stuck model minus best naive predictor", "hl", "claims/id=P3/evidence/markov/est", "claims/id=P3/evidence/markov/ci"),
    ("P3-latent", "latent-skill world: stuck model minus best naive predictor", "hl", "claims/id=P3/evidence/latent_skill/est", "claims/id=P3/evidence/latent_skill/ci"),
    ("P3-process", "process-trace world: stuck model minus best naive predictor", "hl", "claims/id=P3/evidence/process_trace/est", "claims/id=P3/evidence/process_trace/ci"),
    ("P5", "v1 world: time-to-progress head minus Kaplan-Meier (truncated CRPS, s)", "hl", "claims/id=P5/evidence/est", "claims/id=P5/evidence/ci"),
    ("P6a", "error risk, no change: model minus online base rate (log loss)", "hl", "claims/id=P6a/evidence/vs_online/est", "claims/id=P6a/evidence/vs_online/ci"),
    ("R1", "error risk after the rule change: recalibrated minus frozen model", "hr", "claims/id=R1/evidence/est", "claims/id=R1/evidence/ci"),
    ("R3-markov", "markov world: recalibrated minus frozen model", "hr", "claims/id=R3/evidence/markov/est", "claims/id=R3/evidence/markov/ci"),
    ("R3-latent", "latent-skill world: recalibrated minus frozen model", "hr", "claims/id=R3/evidence/latent_skill/est", "claims/id=R3/evidence/latent_skill/ci"),
    ("R3-process", "process-trace world: recalibrated minus frozen model", "hr", "claims/id=R3/evidence/process_trace/est", "claims/id=R3/evidence/process_trace/ci"),
    ("R5a", "error risk after the change: windowed recalibration minus frozen model", "hr", "claims/id=R5/evidence/vs_model/est", "claims/id=R5/evidence/vs_model/ci"),
    ("R5b", "error risk after the change: windowed recalibration minus growing-window recalibration", "hr", "claims/id=R5/evidence/vs_recal/est", "claims/id=R5/evidence/vs_recal/ci"),
    ("D1", "build timing: shipped rule minus break-even (manual runs per routine)", "hd", "rows/0/primary/est", "rows/0/primary/ci95"),
    ("D2", "review routing at a 30% budget: model minus random (escaped errors per 100)", "hd", "rows/1/primary/est", "rows/1/primary/ci95"),
    ("D3", "background start rule minus run whenever idle (value per day)", "hd", "rows/2/primary/est", "rows/2/primary/ci95"),
    ("D4", "coaching action policy minus rule baseline (reward per decision)", "hd", "rows/3/primary/est", "rows/3/primary/ci95"),
    ("K3", "v1 world: time-to-progress range length, model minus Kaplan-Meier baseline (steps)", "hc", "claims/id=K3/evidence/t1_length_difference", "claims/id=K3/evidence/t1_ci"),
)


def p_from_interval(est: float, lo: float, hi: float, level_z: float = Z95) -> float:
    """Two-sided p-value of "the difference is zero" from a 95% interval, by a normal approximation: standard error = width / (2 x 1.96), z = estimate / standard error.
    An approximation of a person-cluster bootstrap, for reading the order of magnitude only."""
    import math

    se = (hi - lo) / (2.0 * level_z)
    if se <= 0.0:
        return 0.0 if est != 0.0 else 1.0
    return float(math.erfc(abs(est) / se / math.sqrt(2.0)))


def holm(ps: list[float]) -> list[float]:
    """Holm's step-down adjusted p-values (valid under any dependence), returned in the input order."""
    m = len(ps)
    order = sorted(range(m), key=lambda i: ps[i])
    out = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * ps[i]))
        out[i] = running
    return out


def _fmt_p(p: float) -> str:
    return "<0.0001" if p < 1e-4 else f"{p:.4f}" if p < 0.01 else f"{p:.3f}"


def _fmt_est(x: float) -> str:
    return f"{x:+.2f}" if abs(x) >= 10 else f"{x:+.3f}"


def holm_family() -> dict[str, Any]:
    """The Holm table over HOLM_ROWS (rows whose part has not run are left out and the family size says so), with the family size and the note on what it is."""
    rows = []
    for rid, label, src, p_est, p_ci in HOLM_ROWS:
        try:
            est, ci = float(resolve(src, p_est)), [float(x) for x in resolve(src, p_ci)]
        except Unresolved:
            continue
        rows.append({"id": rid, "label": label, "est": est, "ci": ci, "p": p_from_interval(est, ci[0], ci[1])})
    adj = holm([r["p"] for r in rows])
    for r, a in zip(rows, adj):
        r["p_holm"] = a
        r["survives"] = bool(a < 0.05)
    lines = ["| Id | Contrast (paired, same resamples) | Estimate [95% interval] | Raw p | Holm-adjusted p | Holds at 5% after Holm |", "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['id']} | {r['label']} | {_fmt_est(r['est'])} [{_fmt_est(r['ci'][0])}, {_fmt_est(r['ci'][1])}] | {_fmt_p(r['p'])} | {_fmt_p(r['p_holm'])} | {'yes' if r['survives'] else '**no**'} |")
    note = ("Raw p is a normal approximation to the reported 95% interval (standard error = width / 3.92), so it is for reading the order of magnitude, not a registered computation: "
            "the registered claims are pass rules on intervals. Holm's step-down is valid under any dependence between the contrasts, which these have (they share worlds and resamples).")
    return {"m": len(rows), "rows": rows, "survivors": sum(r["survives"] for r in rows), "table": "\n".join(lines), "note": note}


def load(src: str) -> Any:
    if src == "hm":
        if "hm" not in _cache:
            _cache["hm"] = holm_family()
        return _cache["hm"]
    if src not in SOURCES:
        raise Unresolved(f"unknown source {src!r}")
    if src not in _cache:
        path, top = SOURCES[src]
        if not path.exists():
            raise Unresolved(f"{path.relative_to(ROOT)} does not exist")
        d = json.loads(path.read_text(encoding="utf-8"))
        _cache[src] = d[top] if top else d
    return _cache[src]


def resolve(src: str, path: str) -> Any:
    node = load(src)
    for seg in path.split("/"):
        if isinstance(node, list):
            if seg == "#len":
                node = len(node)
            elif seg == "#passed":
                node = sum(1 for x in node if isinstance(x, dict) and x.get("pass") is True)
            elif seg == "#failed":
                node = sum(1 for x in node if isinstance(x, dict) and x.get("pass") is False)
            elif seg.startswith("id="):
                hit = [x for x in node if isinstance(x, dict) and x.get("id") == seg[3:]]
                if not hit:
                    raise Unresolved(f"{src}:{path}: no list item with id {seg[3:]}")
                node = hit[0]
            else:
                try:
                    node = node[int(seg)]
                except (ValueError, IndexError) as e:
                    raise Unresolved(f"{src}:{path}: bad list index {seg!r}") from e
        elif isinstance(node, dict):
            if seg not in node:
                raise Unresolved(f"{src}:{path}: no key {seg!r} (have {sorted(node)[:12]})")
            node = node[seg]
        else:
            raise Unresolved(f"{src}:{path}: {seg!r} is below a scalar")
    return node


def fmt(v: Any, spec: str | None) -> str:
    if v is None:
        raise Unresolved("value is null")
    if spec in (None, "raw"):
        return str(v)
    if spec == "word":
        return str(v).replace("_", " ")
    if spec == "base":
        return {"online_base": "online base rate", "frozen_tsp": "frozen time since progress", "frozen_base": "frozen base rate", "frozen_km": "Kaplan-Meier constant"}.get(str(v), str(v).replace("_", " "))
    if spec == "yn":
        return "yes" if v else "no"
    if spec == "held":
        return "passed" if v else "did not pass"
    if spec.startswith("f"):
        return f"{float(v):.{int(spec[1:])}f}"
    if spec.startswith("s"):
        return f"{float(v):+.{int(spec[1:])}f}"
    if spec.startswith("pci"):
        nd = int(spec[3:])
        return f"[{100 * float(v[0]):.{nd}f}%, {100 * float(v[1]):.{nd}f}%]"
    if spec.startswith("p"):
        return f"{100 * float(v):.{int(spec[1:])}f}%"
    if spec == "i":
        return f"{int(round(float(v))):,}"
    if spec.startswith("ci"):
        nd = int(spec[2:])
        return f"[{float(v[0]):.{nd}f}, {float(v[1]):.{nd}f}]"
    raise Unresolved(f"unknown format {spec!r}")


def _operand(tok: str) -> float:
    if ":" in tok:
        src, path = tok.split(":", 1)
        return float(resolve(src, path))
    return float(tok)


def check_asserts(template: str) -> list[str]:
    bad = []
    for m in ASSERT.finditer(template):
        a, op, b = m.group(1), m.group(2), m.group(3)
        try:
            x, y = _operand(a), _operand(b)
        except (Unresolved, TypeError, ValueError) as e:
            bad.append(f"assert {a} {op} {b}: {e}")
            continue
        if not (x < y if op == "<" else x > y):
            bad.append(f"assert {a} {op} {b} is false ({x:.6g} {op} {y:.6g}): a sentence in the template no longer matches the report")
    return bad


def render(template: str) -> tuple[str, list[str]]:
    bad: list[str] = check_asserts(template)

    def sub(m: re.Match) -> str:
        src, path, spec = m.group(1), m.group(2).strip(), m.group(3)
        try:
            return fmt(resolve(src, path), spec)
        except Unresolved as e:
            bad.append(str(e))
            return f"[[UNRESOLVED {src}:{path}]]"
        except (TypeError, ValueError) as e:
            bad.append(f"{src}:{path}|{spec}: {type(e).__name__}: {e}")
            return f"[[UNRESOLVED {src}:{path}]]"

    return PLACEHOLDER.sub(sub, template), bad


HEADER = ("<!-- Generated by scripts/hrt_brief.py from docs/hrt/HRT_BRIEF.tmpl.md. Every number is read from a report under evals/; do not edit this file by hand: "
          "edit the template and run `python3 scripts/hrt_brief.py`. -->\n\n")


CLAIMS_TEMPLATE = ROOT / "docs" / "hrt" / "CLAIMS_HRT.tmpl.md"
CLAIMS_OUT = ROOT / "docs" / "drafts" / "CLAIMS_HRT.md"
JOBS = ((TEMPLATE, OUT, HEADER), (CLAIMS_TEMPLATE, CLAIMS_OUT, HEADER.replace("HRT_BRIEF.tmpl.md", "CLAIMS_HRT.tmpl.md")))


def build() -> tuple[str, list[str]]:
    text, bad = render(TEMPLATE.read_text(encoding="utf-8"))
    return HEADER + text, bad


def build_all() -> list[tuple[Path, str, list[str], int]]:
    """Every generated document: (output path, text, problems, number of generated values)."""
    out = []
    for tmpl, dest, head in JOBS:
        src = tmpl.read_text(encoding="utf-8")
        text, bad = render(src)
        out.append((dest, head + text, bad, len(PLACEHOLDER.findall(src))))
    return out


def main(argv: list[str]) -> int:
    jobs = build_all()
    problems = [(d, b) for d, _, bad, _ in jobs for b in bad]
    if problems:
        print("unresolved placeholders or false assertions:", file=sys.stderr)
        for d, b in problems:
            print(f"  {d.relative_to(ROOT)}: {b}", file=sys.stderr)
        return 2
    if "--check" in argv:
        stale = [d for d, text, _, _ in jobs if (d.read_text(encoding="utf-8") if d.exists() else "") != text]
        if stale:
            print(f"{', '.join(str(d.relative_to(ROOT)) for d in stale)} differ from a fresh render: a report changed. Run `make hrt-brief` and commit the result.", file=sys.stderr)
            return 1
        print("generated documents are current")
        return 0
    for d, text, _, n in jobs:
        d.write_text(text, encoding="utf-8")
        print(f"wrote {d.relative_to(ROOT)} ({len(text.splitlines())} lines, {n} generated numbers)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
