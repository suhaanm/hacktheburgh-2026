"""Pieces of the runner that need no browser: the study-mode request, the world's URLs and ports, the participant rows."""
from __future__ import annotations

from evals.study_roles import analysis_rows as AR
from evals.study_roles import runner as RN
from evals.study_roles.coach_roles import NudgeCounts
from evals.study_roles.roles import cfg, world_port
from evals.study_sim.coach import Shown


def test_study_mode_request_carries_the_skill_and_steps_off(specs, monkeypatch):
    sent = {}

    class R:
        def raise_for_status(self): pass
        def json(self): return {}

    monkeypatch.setattr(RN.httpx, "post", lambda url, json=None, timeout=0: sent.update(url=url, body=json) or R())
    coached = next(s for s in specs if s.arm == "coached")
    slots = coached.slots()
    practice = next(x for x in slots if x.coach_on)
    RN.set_study_mode("http://127.0.0.1:1", coached.person, practice, coached.pid)
    b = sent["body"]
    assert sent["url"].endswith("/study/mode") and b["block"] == "train" and b["skill_on"] == practice.skill_id and b["level"] == "L1" and b["steps_off"] == practice.steps_off
    pre = slots[0]
    RN.set_study_mode("http://127.0.0.1:1", coached.person, pre, coached.pid)
    assert sent["body"]["block"] == "post_test" and sent["body"]["skill_on"] is None
    unc = next(x for x in slots if x.phase == "practice" and not x.coach_on)
    RN.set_study_mode("http://127.0.0.1:1", coached.person, unc, coached.pid)
    assert sent["body"]["block"] == "off" and sent["body"]["skill_on"] is None


def test_world_urls_and_private_ports(role):
    w = RN.RoleWorld(role, "w0", world_port(role, 0), "/tmp/x")
    assert w.case_url("t", 2) == f"http://127.0.0.1:{w.port}/task/t/2" and "layout=v2" in w.case_url("t", 1, layout="v2") and "glitch=503once" in w.case_url("t", 1, glitch="503once")
    assert w.allowed_ports() == {w.port}
    ports = [world_port(role, k) for k in range(8)]
    assert ports == sorted(set(ports)) and all(p not in (7700, 7710, 5173, 7801, 7802, 7803) and not 7911 <= p <= 7933 for p in ports)
    assert min(ports) == (7941 if role == "programmer" else 7951)


def test_block_rows_carry_points_outcomes_and_never_seconds(specs):
    spec = specs[0]

    def case(block, phase, points, outcome, used=10, skill=1):
        c = RN.CaseResult(phase=phase, block=block, reason="done", used=used, wall_s=20.0)
        c.verdict = {"outcome": outcome, "points": points, "claimed_done": True, "skill_check_done": bool(skill), "edge_cases_missed": outcome == "partial"}
        return c

    cases = [case(1, "pre", 0, "claimed_done_wrong", skill=0), case(1, "practice", 1, "partial"), case(1, "post", 2, "correct"), case(2, "pre", 1, "partial"), case(2, "practice", 2, "correct"), case(2, "post", 1, "partial")]
    sh = Shown("d", "annotate", "m", "edge_probe", "probe_edges", "boundary", [], "expert_policy", 0.0, 0.0, ring_found=True, outcome="followed")
    cases[1].shown = [sh]
    rows = AR.block_rows(spec, cases, "m", "")
    r = rows[0]
    assert r["post_checks_done"] == 2 and r["post_checks_possible"] == 2 and r["pre_points"] == 0 and r["pre_outcome"] == "claimed_done_wrong" and r["pre_claimed_done_wrong"] == 1
    assert r["effort_unit"] == "actions" and r["practice_seconds"] == 10 and r["post_outcome"] == "correct" and r["post_skill_check"] == 1 and r["pre_skill_check"] == 0
    assert r["nudges_shown"] == 1 and r["nudges_followed"] == 1 and r["rings_drawn"] == 1 and r["condition"] == spec.blocks[0].nominal_condition
    assert rows[1]["post_checks_done"] == 1 and rows[1]["post_edge_missed"] == 1 and set(r) >= set(AR.COLUMNS)


def test_the_cap_of_every_case_is_at_least_three_times_the_scripted_oracle_path(role):
    from evals.study_roles.roles import CAP_MIN, CAP_MULTIPLE, case_cap, oracle_path_length
    sb = cfg(role).sandbox
    caps = []
    for tid, t in sb.TASKS.items():
        for v in t.variants:
            path = oracle_path_length(role, tid, v)
            cap = case_cap(role, tid, v)
            assert path == max(len(sb.program(tid, v, "expert", variation=k)) for k in range(4))
            assert cap >= CAP_MULTIPLE * path and cap >= CAP_MIN and cap == max(CAP_MIN, CAP_MULTIPLE * path)
            caps.append((path, cap))
    assert (CAP_MULTIPLE, CAP_MIN) == (3, 30) and len(caps) == 12 and max(c for _, c in caps) >= 60
