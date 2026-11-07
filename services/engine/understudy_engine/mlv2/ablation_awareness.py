"""M1 adapter for the AWARENESS track's synthetic cursor features (PLAN.md section 6.1).

Builds the 25 ``aw_*`` columns for every bin of a bin table from ``awareness.synth.make`` (deterministic synthetic awareness events planted
around each persona's planted stuck spells) and ``awareness.features.features_by_bin`` (uses only events that ended before the bin start, so no
future event leaks into a bin). The groups are the plan's: cursor, app kind, glance enum, and all.

HONESTY: the coupling between a stuck spell and cursor behaviour is ASSUMED by the awareness generator (strength per persona, 25% quiet spells,
4% false alarms). A lift in the ablation shows only that the pipeline can use a planted signal; it says nothing about real cursors.
The awareness events are produced for each replicate person from that person's own persona truth (planted spells), in a temporary directory.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np

from understudy_engine.hazard.features import BinTable
from understudy_engine.mlv2 import splits

AWARENESS_NOTE = ("The link between planted stuck spells and cursor behaviour is assumed by the awareness generator; a lift here shows the pipeline "
                  "can use a planted signal, not that real cursors predict being stuck.")


def groups_of(columns: tuple[str, ...]) -> dict[str, list[int]]:
    """Column indices of each group (the plan's: cursor, app kind, glance enum, all)."""
    cursor = {"aw_coverage", "aw_dwell_share", "aw_dwell_s_max", "aw_wander_mean_log", "aw_wander_max_log", "aw_back_forth_sum",
              "aw_speed_bursts_sum", "aw_idle_gap_max_s", "aw_sys_idle_mean_log", "aw_input_active_share", "aw_zone_alternation"}
    app = {c for c in columns if c.startswith("aw_app_")}
    glance = {"aw_glance_any", "aw_glance_blocked", "aw_glance_conf", "aw_trigger_hotkey", "aw_trigger_loop"}
    idx = {c: i for i, c in enumerate(columns)}
    return {
        "cursor": [idx[c] for c in columns if c in cursor],
        "app_kind": [idx[c] for c in columns if c in app],
        "glance": [idx[c] for c in columns if c in glance],
        "all": list(range(len(columns))),
    }


def awareness_events_for(slug: str, r: int, kind: str, n_days: int = 21) -> tuple[list[dict], str]:
    """Synthetic awareness events for one persona draw. Returns (events, person id)."""
    import dataclasses

    from understudy_engine.awareness import synth
    from understudy_engine.personas import simulate_persona

    spec = splits.persona_spec(slug, r, kind)
    run = simulate_persona(spec, n_days, with_mc=False)
    with tempfile.TemporaryDirectory(prefix="mlv2-aw-") as td:
        d = Path(td) / "synthetic" / slug
        d.mkdir(parents=True)
        with (d / "events.jsonl").open("w", encoding="utf-8") as fh:
            for row in run.rows:
                fh.write(json.dumps(row) + "\n")
        (d / "truth.json").write_text(json.dumps(run.truth))
        res = synth.make(slug, root=td)
    return res.events, spec.person


def awareness_matrix(tab: BinTable, members: list[tuple[str, int, str]], n_days: int = 21) -> tuple[np.ndarray, tuple[str, ...]]:
    """(n_bins, 25) matrix of awareness columns aligned with the rows of ``tab`` (people not in ``members`` get zeros, so pass the pool)."""
    from understudy_engine.awareness.features import AWARENESS_COLUMNS, features_by_bin

    out = np.zeros((tab.n, len(AWARENESS_COLUMNS)))
    for slug, r, kind in members:
        events, person = awareness_events_for(slug, r, kind, n_days)
        rows = tab.rows_of([person])
        if rows.size == 0:
            continue
        fb = features_by_bin(events, tab.t[rows].tolist())
        out[rows] = np.array([[f[c] for c in AWARENESS_COLUMNS] for f in fb])
    return out, tuple(AWARENESS_COLUMNS)


def awareness_groups(tab: BinTable, members: list[tuple[str, int, str]], n_days: int = 21) -> dict[str, np.ndarray]:
    X, cols = awareness_matrix(tab, members, n_days)
    g = groups_of(cols)
    return {name: X[:, ix] for name, ix in g.items()}


def planted_spells_for(members: list[tuple[str, int, str]], n_days: int = 21) -> dict[str, list[tuple[float, float]]]:
    """Planted stuck spells (unix seconds) per person for a pool, from the persona generator's own truth (what the awareness events were
    planted against)."""
    import datetime as _dt

    from understudy_engine.personas import simulate_persona

    def ts(s: str) -> float:
        return _dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()

    out: dict[str, list[tuple[float, float]]] = {}
    for slug, r, kind in members:
        spec = splits.persona_spec(slug, r, kind)
        run = simulate_persona(spec, n_days, with_mc=False)
        out[spec.person] = [(ts(s["t0"]), ts(s["t1"])) for s in run.truth.get("stuck_episodes", [])]
    return out


def planted_label_table(tab: BinTable, spells: dict[str, list[tuple[float, float]]]) -> BinTable:
    """The bin table with its label replaced by 'a planted spell overlaps the 60 s after the bin' (v1's ``vs_planted`` label).

    SUPPLEMENTARY ablation target (PLAN.md amendment 5): the awareness events were planted against planted spells, not against the
    'no progress in 60 s' label the hazard model is trained on, so the primary ablation can show no lift even though the pipeline could use
    the signal. This target asks the other question: can the pipeline use the planted signal when the label is the thing it was planted for."""
    import dataclasses

    y = np.zeros(tab.n, dtype=tab.y.dtype)
    for q, sp in spells.items():
        rows = tab.rows_of([q])
        if not rows.size or not sp:
            continue
        t = tab.t[rows]
        for t0, t1 in sp:
            y[rows[(t + tab.horizon_s > t0) & (t < t1)]] = 1
    return dataclasses.replace(tab, y=y)
