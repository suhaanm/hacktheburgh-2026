from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from evals.study_sim import analysis_io  # noqa: E402
from evals.study_sim.design import build_participants  # noqa: E402


@pytest.fixture(scope="session")
def specs():
    return build_participants()


def made_up_rows(specs, score_fn, *, aa_score_fn=None, actions=lambda spec, b, phase: 20):
    """CSV-shaped rows for every participant, scores from score_fn(spec, block) (made-up numbers for the tests only)."""
    rows = []
    for s in specs:
        fn = score_fn if s.arm == "coached" else (aa_score_fn or score_fn)
        for b in s.blocks:
            done = fn(s, b)
            possible = 2 if b.skill == "cliff" else 1
            rows.append({
                "participant": s.pid, "sequence": s.sequence, "block": float(b.block), "skill": b.skill, "condition": b.nominal_condition,
                "practice_case": b.practice_case, "post_case": b.post_case, "practice_seconds": float(actions(s, b, "practice")), "practice_capped": False,
                "post_seconds": float(actions(s, b, "post")), "post_capped": False, "post_checks_done": float(min(done, possible)),
                "post_checks_possible": float(possible), "nudges_shown": 2.0 if b.actual_condition == "coached" else 0.0,
                "nudges_followed": 1.0 if b.actual_condition == "coached" else 0.0, "nudges_dismissed": 1.0 if b.actual_condition == "coached" else 0.0,
                "exclusion": "", "notes": "", "arm": s.arm, "persona": s.persona.code(), "model": "test-model", "effort_unit": "actions",
                "actual_condition": b.actual_condition, "case_variant": s.variant, "practice_actions": float(actions(s, b, "practice")),
                "post_actions": float(actions(s, b, "post")), "nudges_ignored": 0.0, "false_nudges": 0.0, "lag_prompts": 0.0, "rings_drawn": 1.0})
    return rows


def write_rows_csv(path: Path, rows: list[dict]) -> None:
    out = []
    for r in rows:
        r = dict(r)
        r["practice_capped"] = "yes" if r["practice_capped"] else "no"
        r["post_capped"] = "yes" if r["post_capped"] else "no"
        out.append(r)
    analysis_io.write_csv(path, out)
