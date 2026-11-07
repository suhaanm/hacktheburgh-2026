"""CSV rows of the role studies: the human-study format of ``evals/study/analyze.py`` (so its helpers run unchanged on them) plus the columns this design adds
(pre-test, outcome words, process flags). ``post_checks_done`` holds the ORACLE POINTS of the post-test (0, 1 or 2, out of ``post_checks_possible`` = 2); effort columns hold
ACTION COUNTS, never seconds."""
from __future__ import annotations

import csv
from pathlib import Path

from evals.study_sim import analysis_io as sim_io
from .coach_roles import NudgeCounts
from .design import ParticipantSpec

HUMAN = ["participant", "sequence", "block", "skill", "condition", "practice_case", "post_case", "practice_seconds", "practice_capped", "post_seconds", "post_capped",
         "post_checks_done", "post_checks_possible", "nudges_shown", "nudges_followed", "nudges_dismissed", "exclusion", "notes"]
EXTRA = ["role", "arm", "unit", "persona", "model", "tier", "effort_unit", "actual_condition", "pre_case", "pre_points", "pre_outcome", "pre_skill_check", "pre_actions", "pre_capped",
         "practice_points", "practice_outcome", "practice_actions", "post_outcome", "post_skill_check", "post_actions", "post_claimed_done", "post_edge_missed", "pre_claimed_done_wrong",
         "post_claimed_done_wrong", "practice_end", "pre_end", "post_end", "protocol_violation", "nudges_ignored", "false_nudges", "lag_prompts", "rings_drawn", "banners_only", "zone_ok",
         "pre_wall_s", "practice_wall_s", "post_wall_s", "worker"]
COLUMNS = HUMAN + EXTRA
NUMERIC_EXTRA = ["unit", "pre_points", "pre_skill_check", "pre_actions", "practice_points", "practice_actions", "post_skill_check", "post_actions", "post_claimed_done", "post_edge_missed",
                 "pre_claimed_done_wrong", "post_claimed_done_wrong", "nudges_ignored", "false_nudges", "lag_prompts", "rings_drawn", "banners_only", "zone_ok", "pre_wall_s",
                 "practice_wall_s", "post_wall_s"]


def _case_bits(c) -> dict:
    v = (c.verdict or {}) if c else {}
    return {"points": v.get("points", 0) if c and c.verdict else 0, "outcome": v.get("outcome", "no_result") if c and c.verdict else "no_result",
            "skill": int(bool(v.get("skill_check_done"))), "claimed": int(bool(v.get("claimed_done"))), "edge": int(bool(v.get("edge_cases_missed"))),
            "cdw": int(v.get("outcome") == "claimed_done_wrong")}


def block_rows(spec: ParticipantSpec, cases: list, model_id: str, exclusion: str) -> list[dict]:
    by = {(c.block, c.phase): c for c in cases}
    rows = []
    for b in spec.blocks:
        pre, pr, po = by.get((b.block, "pre")), by.get((b.block, "practice")), by.get((b.block, "post"))
        n = NudgeCounts.of(pr.shown, spec.role) if pr else NudgeCounts()
        a, p, q = _case_bits(pre), _case_bits(pr), _case_bits(po)
        viol = "; ".join(x for x in (pre.protocol_violation if pre else "", pr.protocol_violation if pr else "", po.protocol_violation if po else "") if x)
        rows.append({
            "participant": spec.pid, "sequence": spec.sequence, "block": b.block, "skill": b.skill, "condition": b.nominal_condition,
            "practice_case": f"{b.practice[0]}/v{b.practice[1]}", "post_case": f"{b.post[0]}/v{b.post[1]}",
            "practice_seconds": pr.used if pr else 0, "practice_capped": "yes" if (pr and pr.capped) else "no", "post_seconds": po.used if po else 0, "post_capped": "yes" if (po and po.capped) else "no",
            "post_checks_done": q["points"], "post_checks_possible": 2, "nudges_shown": n.shown, "nudges_followed": n.followed, "nudges_dismissed": n.dismissed,
            "exclusion": exclusion, "notes": f"actual={b.actual_condition}" + (f"; protocol violation: {viol}" if viol else ""),
            "role": spec.role, "arm": spec.arm, "unit": spec.unit, "persona": spec.persona.code(), "model": model_id, "tier": spec.tier, "effort_unit": "actions", "actual_condition": b.actual_condition,
            "pre_case": f"{b.pre[0]}/v{b.pre[1]}", "pre_points": a["points"], "pre_outcome": a["outcome"], "pre_skill_check": a["skill"], "pre_actions": pre.used if pre else 0,
            "pre_capped": "yes" if (pre and pre.capped) else "no", "practice_points": p["points"], "practice_outcome": p["outcome"], "practice_actions": pr.used if pr else 0,
            "post_outcome": q["outcome"], "post_skill_check": q["skill"], "post_actions": po.used if po else 0, "post_claimed_done": q["claimed"], "post_edge_missed": q["edge"],
            "pre_claimed_done_wrong": a["cdw"], "post_claimed_done_wrong": q["cdw"], "practice_end": pr.reason if pr else "", "pre_end": pre.reason if pre else "", "post_end": po.reason if po else "",
            "protocol_violation": viol, "nudges_ignored": n.ignored, "false_nudges": n.false_nudges, "lag_prompts": n.lag_prompts, "rings_drawn": n.rings_drawn, "banners_only": n.banners_only,
            "zone_ok": n.zone_ok, "pre_wall_s": pre.wall_s if pre else 0, "practice_wall_s": pr.wall_s if pr else 0, "post_wall_s": po.wall_s if po else 0, "worker": spec.worker})
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    real = sim_io.check_output_dir(Path(path).parent) / Path(path).name
    real.parent.mkdir(parents=True, exist_ok=True)
    with real.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def append_csv(path: Path, rows: list[dict]) -> None:
    real = sim_io.check_output_dir(Path(path).parent) / Path(path).name
    exists = real.exists()
    real.parent.mkdir(parents=True, exist_ok=True)
    with real.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        if not exists:
            w.writeheader()
        w.writerows(rows)


def load_rows(path: Path) -> list[dict]:
    """The CSV as rows with the numeric columns as floats (``analyze.load`` for the human columns, the rest here)."""
    import sys

    sys.path.insert(0, str(sim_io.STUDY))
    import analyze as A  # noqa: PLC0415

    rows = A.load(Path(path))
    for r in rows:
        for k in NUMERIC_EXTRA:
            try:
                r[k] = float(r[k]) if r.get(k, "") != "" else 0.0
            except ValueError:
                r[k] = 0.0
    return rows
