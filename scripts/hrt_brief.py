#!/usr/bin/env python3
"""Render docs/HRT_BRIEF.md from docs/hrt/HRT_BRIEF.tmpl.md, filling every number from the reports under evals/.

No number in the brief is typed by hand. A placeholder is ``{{src:path/to/value|fmt}}``:

  src   one of  r (evals/report.json, from its ``sections``)  rt (evals/report.json, top level)  hl (evals/hrt/results/heldout_ledger.json)
        hd (evals/hrt/results/heldout_decisions.json)  hr (evals/hrt/results/heldout_recal.json)  mh (evals/mlv2/results/heldout_hazard.json)  mm (evals/mlv2/results/heldout_mismatch.json)
        cue (evals/cue/held_out.json)
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
    "mh": (ROOT / "evals" / "mlv2" / "results" / "heldout_hazard.json", None),
    "mm": (ROOT / "evals" / "mlv2" / "results" / "heldout_mismatch.json", None),
    "cue": (ROOT / "evals" / "cue" / "held_out.json", None),
}
ASSERT = re.compile(r"<!--\s*assert\s+(\S+)\s*([<>])\s*(\S+?)\s*-->")
PLACEHOLDER = re.compile(r"\{\{\s*([a-z]+):([^|}]+?)\s*(?:\|\s*([a-z0-9]+))?\s*\}\}")
_cache: dict[str, Any] = {}


class Unresolved(KeyError):
    pass


def load(src: str) -> Any:
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
