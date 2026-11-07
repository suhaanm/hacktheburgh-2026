from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
for p in (ROOT, ROOT / "services" / "agent"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import pytest  # noqa: E402

from evals.study_roles.design import build_participants  # noqa: E402
from evals.study_roles.roles import ROLE_CFG  # noqa: E402


@pytest.fixture(params=list(ROLE_CFG))
def role(request):
    return request.param


@pytest.fixture()
def specs(role):
    return build_participants(role)


def made_up_rows(specs, post_fn, *, pre_fn=lambda s, b: 0, aa_post_fn=None):
    """CSV-shaped rows (floats, as ``load_rows`` returns them) from made-up point functions of (spec, block). For the tests only."""
    rows = []
    for s in specs:
        fn = post_fn if s.arm == "coached" else (aa_post_fn or post_fn)
        for b in s.blocks:
            post, pre = fn(s, b), pre_fn(s, b)
            rows.append({
                "participant": s.pid, "sequence": s.sequence, "block": float(b.block), "skill": b.skill, "condition": b.nominal_condition,
                "practice_case": f"{b.practice[0]}/v{b.practice[1]}", "post_case": f"{b.post[0]}/v{b.post[1]}", "practice_seconds": 20.0, "practice_capped": False, "post_seconds": 18.0, "post_capped": False,
                "post_checks_done": float(post), "post_checks_possible": 2.0, "nudges_shown": 1.0 if b.actual_condition == "coached" else 0.0,
                "nudges_followed": 1.0 if b.actual_condition == "coached" else 0.0, "nudges_dismissed": 0.0, "exclusion": "", "notes": "",
                "role": s.role, "arm": s.arm, "unit": float(s.unit), "persona": s.persona.code(), "model": "test-model", "tier": "fake", "effort_unit": "actions", "actual_condition": b.actual_condition,
                "pre_case": f"{b.pre[0]}/v{b.pre[1]}", "pre_points": float(pre), "pre_outcome": "wrong", "pre_skill_check": 0.0, "pre_actions": 20.0, "pre_capped": "no",
                "practice_points": 1.0, "practice_outcome": "partial", "practice_actions": 20.0, "post_outcome": ["wrong", "partial", "correct"][int(post)], "post_skill_check": 1.0 if post == 2 else 0.0,
                "post_actions": 18.0, "post_claimed_done": 1.0, "post_edge_missed": 0.0, "pre_claimed_done_wrong": 0.0, "post_claimed_done_wrong": 0.0, "nudges_ignored": 0.0, "false_nudges": 0.0,
                "lag_prompts": 0.0, "rings_drawn": 1.0, "banners_only": 0.0, "zone_ok": 1.0, "pre_wall_s": 40.0, "practice_wall_s": 40.0, "post_wall_s": 40.0})
    return rows
