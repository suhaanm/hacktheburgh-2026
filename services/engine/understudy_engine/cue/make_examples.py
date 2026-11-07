"""Writes example payloads for the other tracks (the dashboard's Growth screen and the desktop's Cue parser) into ``packages/schema/examples/``.

SYNTHETIC: a simulated improving learner (``simlearn``, seed fixed) and the mock-mode fixtures. Deterministic, so the files only change when
the code does. ``python -m understudy_engine.cue.make_examples``.
"""
from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from . import fixtures as FX
from . import ledger as L
from . import paths as P
from . import score as S
from . import simlearn as SL
from .live import LiveCue
from .routes import _meta


def build_decisions() -> dict:
    """The Cue decision walks over the mock-mode fixtures, one per scenario. Each non-silent poll carries ``step`` with its ``target`` (the pack's zone)."""
    decisions = {}
    live = LiveCue()
    import os

    old = os.environ.get("UNDERSTUDY_MOCK")
    os.environ["UNDERSTUDY_MOCK"] = "1"
    try:
        for name, ts in (("stuck_after_result", (0, 60, 85, 87.5, 90, 105, 120)), ("close_call", (0, 60, 85, 87.5)), ("retrieval", (0, 60)), ("level_4", (0,))):
            seq = []
            for t in ts:
                env = live.next(f"p_ex_{name}", fixture=name, fixture_t=t)
                seq.append({"t": t, **env["data"]})
            decisions[name] = {"meta": env["meta"], "polls": seq}
    finally:
        if old is None:
            os.environ.pop("UNDERSTUDY_MOCK", None)
        else:
            os.environ["UNDERSTUDY_MOCK"] = old
    return decisions


def build() -> dict[str, dict]:
    rows, _truth = SL.simulate_learner(SL.preset("improving"), np.random.default_rng(21), person="p_sim_learner", n_per_skill=30)
    now = S.row_time(S.assist_only(rows)[-1]) + 1800.0
    offloaded = [L.make_row(person="p_sim_learner", role="benefits-processor", skill="enter-household-once", t=now - 3600 * (i + 1) * 5, outcome="clean", stream="automation" if i % 2 else "delegated",
                            routine="calc-entry-3x", minutes=12.0 + i, offload_outcome="done", origin="synthetic", origin_detail="synthetic_learner", serial=900 + i) for i in range(4)]
    allrows = rows + offloaded
    g = S.growth(allrows, person="p_sim_learner", now=now, n_boot=200)          # the same ledger the ledger example shows: offloaded rows are listed, never scored
    growth = {"meta": _meta(g["_origin"], g["_n"], g["_note"], g["_split"]), "data": {k: v for k, v in g.items() if not k.startswith("_")}}
    skill = S.growth(allrows, person="p_sim_learner", skill="check-the-cliff", now=now, n_boot=120)
    growth_skill = {"meta": _meta(skill["_origin"], skill["_n"], skill["_note"], skill["_split"]), "data": {k: v for k, v in skill.items() if not k.startswith("_")}}
    newest = sorted(allrows, key=lambda r: r["t_hour"], reverse=True)[:60]
    counts = {s: sum(1 for r in allrows if r["stream"] == s) for s in ("assist", "delegated", "automation")}
    ledger = {"meta": _meta("synthetic", counts["assist"], "Enums and numbers only: no text, no screenshots."), "data": {"rows": newest, "counts": counts}}
    return {"cue.growth.example.json": growth, "cue.growth_skill.example.json": growth_skill, "cue.ledger.example.json": ledger,
            "cue.decisions.example.json": build_decisions()}


def main(only: Sequence[str] = ()) -> int:
    """Write the examples. ``only`` ("decisions") writes just the Cue decision walks and leaves the other files untouched."""
    out = P.repo_root() / "packages" / "schema" / "examples"
    out.mkdir(parents=True, exist_ok=True)
    if set(only) - {"decisions"}:
        raise SystemExit("usage: python -m understudy_engine.cue.make_examples [decisions]")
    docs = {"cue.decisions.example.json": build_decisions()} if only else build()
    for name, doc in docs.items():
        (out / name).write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print("wrote", out / name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
