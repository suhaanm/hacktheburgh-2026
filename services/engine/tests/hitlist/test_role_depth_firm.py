"""RD (7 Nov 2026): the built-in synthetic firm of the hit list shows only the repeated actions the synthetic design plants. The routine templates
written later from the job have no synthetic usage behind them, so the firm must not invent a rate for them."""
from __future__ import annotations

from understudy_engine.hitlist import firm as F
from understudy_engine.memory import load_pack


def test_the_synthetic_firm_has_rows_only_for_planted_templates_and_the_new_templates_are_not_invented():
    people = F.tiny_firm(28)
    seen = {r["id"] for p in people for r in p["rows"]}
    assert seen and seen <= set(F.RUNS_PER_WEEK)
    for role in ("programmer", "data-analyst"):
        pack = load_pack(role)
        new_automatable = {t["id"] for t in pack.templates if t.get("automatable", True) and t["id"] not in F.RUNS_PER_WEEK}
        assert len(new_automatable) >= 6 and not new_automatable & seen


def test_the_firms_rows_for_the_roles_are_what_they_were_before_the_templates_were_added():
    people = F.tiny_firm(28)
    by_role = {role: {r["id"] for p in people if p["role"] == role for r in p["rows"]} for role in ("programmer", "data-analyst", "benefits-processor")}
    assert by_role["programmer"] <= {"rerun-failed-ci"} and by_role["data-analyst"] <= {"weekly-metric-refresh"}
    assert by_role["benefits-processor"] <= {"calc-entry-3x", "case-note-copy", "weekly-report"}
