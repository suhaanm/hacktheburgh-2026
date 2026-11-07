"""HND-2, HND-4: consent modes, typed confirmation, the autonomy ladder, memory read-back, revocation."""
from __future__ import annotations

import json

import pytest

from understudy_engine.memory import MemoryStore, WriteRefused
from understudy_engine.routines.store import CEILING, ConsentError, RoutineStore, line_text, parse_line


def _routine(rid="calc-entry-3x", classes=("submit",), eligible=True, automatable=True, template="calc-entry-3x"):
    return {
        "id": rid, "role": "benefits-processor", "title": "Enter the household into three calculators", "person": "p_me",
        "template_id": template, "episodes": 14, "minutes_per_week": 96.0, "cv": 0.18, "judgement_share": 0.0,
        "value": {"hours_saved": [3.1, 5.2], "net_gbp": [41.0, 90.0], "confidence": 0.82, "horizon_weeks": 4, "assumptions": {}},
        "touches": ["gov.uk check"], "never": ["submit"], "irreversible_classes": list(classes),
        "build_timing": {"rule": "ski-rental", "buy_after_runs": 3, "regret_vs_hindsight": 1.2},
        "skill_gate": {"eligible": eligible, "reason": "mastery L4 on ENTER_HOUSEHOLD" if eligible else "coach first: ENTER_HOUSEHOLD at L2"},
        "automatable": automatable, "proposable": eligible and automatable, "not_proposable_because": [],
        "proposal": {"what": "x", "how_often": "about 14 times in 3 weeks", "touches": [], "never": ["submit"]},
        "signature": ["OPEN", "ENTER", "READ"], "forecast": {}, "last_seen": 0.0,
    }


@pytest.fixture
def env(tmp_path):
    mem = MemoryStore(tmp_path / "home")
    st = RoutineStore(mem, bundle_root=tmp_path / "data" / "routines")
    st.merge([_routine()])
    return mem, st, tmp_path


def test_merge_keeps_the_workers_decisions_and_ids_of_unnamed_routines(env):
    mem, st, _ = env
    st.consent("calc-entry-3x", "shadow", actor="worker")
    st.merge([{**_routine(), "episodes": 20, "minutes_per_week": 120.0}])
    r = st.list()[0]
    assert r["episodes"] == 20 and r["status"] == "shadow" and r["consent"]["mode"] == "shadow"      # measured fields update, consent stays
    st.merge([_routine("auto-aaaaaa", template=None), ])
    st.merge([{**_routine("auto-bbbbbb", template=None), "signature": ["OPEN", "ENTER", "READ", "COPY"]}])   # one step off: same routine
    ids = [r["id"] for r in st.list()]
    assert "auto-aaaaaa" in ids and "auto-bbbbbb" not in ids


def test_consent_modes_status_rung_and_memory_line(env):
    mem, st, tmp = env
    out = st.consent("calc-entry-3x", "shadow", actor="worker")
    assert out["status"] == "shadow" and out["rung"] == "A1" and out["consent"]["mode"] == "shadow"
    lines = [l.text for l in mem.read().section("Routines").lines()]
    assert lines == ["calc-entry-3x | rung A1 | consent: shadow | unattended: not allowed"]
    assert json.loads((tmp / "data" / "routines" / "calc-entry-3x" / "consent.json").read_text())["revoked"] is False
    out = st.consent("calc-entry-3x", "approval", actor="worker")
    assert out["status"] == "approval" and out["rung"] == "A1"          # consent never grants a rung; shadow evidence does
    out = st.consent("calc-entry-3x", "not_now", actor="worker")
    assert out["status"] == "declined" and out["rung"] == "A0"
    assert mem.read().section("Routines").lines() == []                    # the line goes with the consent
    assert json.loads((tmp / "data" / "routines" / "calc-entry-3x" / "consent.json").read_text())["revoked"] is True
    assert st.consent("calc-entry-3x", "never", actor="worker")["status"] == "never"
    with pytest.raises(ConsentError) as e:
        st.consent("calc-entry-3x", "maybe", actor="worker")
    assert e.value.status == 422


def test_model_driven_irreversible_needs_the_typed_confirmation_compiled_needs_one_tap(env):
    mem, st, tmp = env
    with pytest.raises(ConsentError) as e:                                   # model-driven (no bundle on disk): typed confirm required
        st.consent("calc-entry-3x", "unattended", irreversible_unattended=["submit"], actor="worker")
    assert e.value.code == "typed_confirm_required" and e.value.status == 422
    with pytest.raises(ConsentError):
        st.consent("calc-entry-3x", "unattended", irreversible_unattended=["submit"], typed_confirm="yes", actor="worker")
    out = st.consent("calc-entry-3x", "unattended", irreversible_unattended=["submit"], typed_confirm="calc-entry-3x", actor="worker")
    assert out["consent"] == {"mode": "unattended", "irreversible_unattended": ["submit"], "typed_confirm": True} and out["driver"] == "model"
    assert mem.read().section("Routines").lines()[0].text.endswith("unattended: allowed [submit]")
    # a compiled routine (bundle exists) needs only the tap
    b = tmp / "data" / "routines" / "calc-entry-3x"
    b.mkdir(parents=True, exist_ok=True)
    (b / "steps.json").write_text("{}")
    out = st.consent("calc-entry-3x", "unattended", irreversible_unattended=["submit"], actor="worker")
    assert out["driver"] == "compiled" and out["consent"]["irreversible_unattended"] == ["submit"] and out["consent"]["typed_confirm"] is False
    # without any irreversible class, unattended needs nothing extra
    assert st.consent("calc-entry-3x", "unattended", actor="worker")["consent"]["irreversible_unattended"] == []


def test_irreversible_classes_must_exist_and_only_apply_to_unattended(env):
    _, st, _ = env
    with pytest.raises(ConsentError) as e:
        st.consent("calc-entry-3x", "unattended", irreversible_unattended=["pay"], typed_confirm="calc-entry-3x", actor="worker")
    assert e.value.code == "unknown_class"
    with pytest.raises(ConsentError) as e:
        st.consent("calc-entry-3x", "approval", irreversible_unattended=["submit"], actor="worker")
    assert e.value.code == "irreversible_needs_unattended"


def test_skill_gate_blocks_enabling_unless_the_worker_overrides_and_declines_always_work(tmp_path):
    mem = MemoryStore(tmp_path)
    st = RoutineStore(mem, bundle_root=tmp_path / "r")
    st.merge([_routine(eligible=False), _routine("judgy", automatable=False, template="judgy")])
    with pytest.raises(ConsentError) as e:
        st.consent("calc-entry-3x", "shadow", actor="worker")
    assert e.value.code == "skill_gate" and "coach first" in str(e.value)
    assert st.consent("calc-entry-3x", "shadow", skill_override=True, actor="worker")["status"] == "shadow"
    assert "worker override" in mem.read().section("Routines").lines()[0].note
    assert st.consent("calc-entry-3x", "never", actor="worker")["status"] == "never"
    with pytest.raises(ConsentError) as e:
        st.consent("judgy", "shadow", skill_override=True, actor="worker")
    assert e.value.code == "not_automatable"


def test_only_the_worker_can_change_consent(env):
    mem, st, _ = env
    before = mem.path.read_bytes() if mem.path.exists() else b""
    for actor in ("agent", "page", "model", "tool"):
        with pytest.raises(WriteRefused):
            st.consent("calc-entry-3x", "unattended", actor=actor)
    assert (mem.path.read_bytes() if mem.path.exists() else b"") == before
    assert st.list()[0]["consent"]["mode"] == "none"


def test_shadow_ladder_promotes_on_the_wilson_bound_and_demotes_on_failure(env):
    _, st, _ = env
    with pytest.raises(ConsentError) as e:
        st.shadow("calc-entry-3x", matched=True)                            # not switched on yet
    assert e.value.status == 409
    st.consent("calc-entry-3x", "approval", actor="worker")
    for i in range(19):
        out = st.shadow("calc-entry-3x", matched=True)
    assert out["runs"] == 19 and out["rung"] == "A1" and not out["promoted"]   # 19 clean runs: bound 0.832 but fewer than 20 runs
    out = st.shadow("calc-entry-3x", matched=True)
    assert out["runs"] == 20 and out["wilson_lower"] == pytest.approx(0.839, abs=0.002) and out["rung"] == "A2" and out["promoted"]
    out = st.shadow("calc-entry-3x", event="undo")                           # an undo demotes one rung and restarts the count
    assert out["rung"] == "A1" and out["demoted"] and out["runs"] == 0
    out = st.shadow("calc-entry-3x", runs=20, matches=17)                    # 17/20 -> bound 0.64: not enough
    assert out["rung"] == "A1" and out["wilson_lower"] < 0.8
    out = st.shadow("calc-entry-3x", runs=10, matches=10)                    # 27/30 -> 0.74: still short
    assert out["wilson_lower"] < 0.8 and out["rung"] == "A1"
    out = st.shadow("calc-entry-3x", runs=40, matches=40)                    # 67/70 -> 0.88
    assert out["wilson_lower"] >= 0.8 and out["rung"] == "A2" and out["promoted"]


def test_rung_is_capped_by_consent_and_a3_needs_the_higher_bound(env):
    _, st, _ = env
    st.consent("calc-entry-3x", "approval", actor="worker")
    out = st.shadow("calc-entry-3x", runs=100, matches=100)
    assert out["wilson_lower"] > 0.95 and out["rung"] == "A2" and out["ceiling"] == "A2"          # approval caps at A2
    st.consent("calc-entry-3x", "unattended", actor="worker")
    out = st.shadow("calc-entry-3x", runs=0, matches=0)
    assert out["rung"] == "A3"
    with pytest.raises(ConsentError):
        st.shadow("calc-entry-3x", runs=5, matches=9)
    assert CEILING["shadow"] == "A1"


def test_injection_hit_blocks_until_the_worker_switches_it_on_again(env):
    _, st, _ = env
    st.consent("calc-entry-3x", "unattended", actor="worker")
    st.shadow("calc-entry-3x", runs=80, matches=80)
    out = st.shadow("calc-entry-3x", event="injection")
    assert out["rung"] == "A2" and out["demoted"]
    with pytest.raises(ConsentError) as e:
        st.shadow("calc-entry-3x", matched=True)
    assert e.value.code == "blocked" and e.value.status == 409
    st.consent("calc-entry-3x", "shadow", actor="worker")
    assert st.shadow("calc-entry-3x", matched=True)["runs"] == 1


def test_memory_file_can_tighten_but_never_loosen_consent(env):
    mem, st, _ = env
    st.consent("calc-entry-3x", "approval", actor="worker")
    st.shadow("calc-entry-3x", runs=25, matches=25)
    assert st.list()[0]["rung"] == "A2"
    line = mem.read().section("Routines").lines()[0]
    # editing the file looser (rung A3, unattended) does nothing
    mem.update_line(line.id, actor="worker", text="calc-entry-3x | rung A3 | consent: unattended | unattended: allowed [submit]")
    r = st.list()[0]
    assert r["consent"]["mode"] == "approval" and r["rung"] == "A2" and r["consent"]["irreversible_unattended"] == []
    # editing it tighter applies at once
    mem.update_line(line.id, actor="worker", text="calc-entry-3x | rung A1 | consent: shadow | unattended: not allowed")
    r = st.list()[0]
    assert r["consent"]["mode"] == "shadow" and r["rung"] == "A1" and r["status"] == "shadow" and "tighter" in r["note"]
    # deleting the line switches the routine off (MEM-5: deleting a line removes it from behaviour)
    mem.forget(line.id, actor="worker")
    r = st.list()[0]
    assert r["consent"]["mode"] == "not_now" and r["rung"] == "A0" and r["status"] == "declined"


def test_line_round_trip():
    r = {"id": "x-1", "rung": "A2", "consent": {"mode": "unattended", "irreversible_unattended": ["submit", "send"]}}
    p = parse_line(line_text(r))
    assert p == {"id": "x-1", "rung": "A2", "mode": "unattended", "unattended_classes": ["submit", "send"], "unattended": True}
    assert parse_line("nonsense") is None
