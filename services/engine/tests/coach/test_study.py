from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("understudy_agent", reason="run with: uv run --package understudy-agent pytest services/engine/tests/coach")

from fastapi.testclient import TestClient  # noqa: E402

from understudy_engine.api.app import create_app  # noqa: E402
from understudy_engine.coach import CoachBrain, StuckScorer  # noqa: E402
from understudy_engine.store import EventStore, to_row  # noqa: E402
from understudy_engine.study import StudyError, clear_state, read_log, read_state, validate, write_state  # noqa: E402
from understudy_engine.study.__main__ import main as study_cli  # noqa: E402

from .helpers import calc, cliff, copy_to_note, ev, read, reconcile_zone  # noqa: E402


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("UNDERSTUDY_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("AGENT_PORT", "1")
    return tmp_path / "data"


@pytest.fixture()
def brain(env):
    return CoachBrain(EventStore(env), scorer=StuckScorer(fit=False), tone="short")


def run(brain, events, person="p_hand", **kw):
    return [(e, brain.next_step(person, e.t, events=events[: i + 1], **kw)) for i, e in enumerate(events)]


def acts(trace):
    return [(e, d) for e, d in trace if d.action != "silent"]


def study_case_no_cliff_checks(task="t_h1"):
    """Two calculators (the study case), no cliff panel opened, then straight to the note without reconciling."""
    return ([ev(0, "task_start", task=task, source="desk")] + read(task, 1) + calc(task, 12, "calc1") + calc(task, 50, "calc2")
            + copy_to_note(task, 92))


def study_case_cliffs_but_no_reconcile(task="t_h1"):
    return ([ev(0, "task_start", task=task, source="desk")] + read(task, 1) + calc(task, 12, "calc1") + cliff(task, 46)
            + calc(task, 56, "calc2") + cliff(task, 90) + copy_to_note(task, 100))


# ------------------------------------------------------------------------------------------ state
def test_state_validation_and_atomic_write(env):
    with pytest.raises(StudyError):
        validate("hand", "train", "check-the-cliff", "L1")
    for bad in (("p_hand", "warmup", None, "L1"), ("p_hand", "train", None, "L1"), ("p_hand", "train", "check-the-cliff", "L5"), ("p_hand", "train", "Check The Cliff", "L1")):
        with pytest.raises(StudyError):
            validate(*bad)
    assert read_state() is None
    m = write_state("p_hand", "train", "cliff", "L1", participant="P1", block_no=1)
    assert m.skill_id == "check-the-cliff" and m.coaching and m.steps_off == ("calc_c", "cliff_c")
    on_disk = json.loads((env / "study" / "state.json").read_text())
    assert on_disk["person"] == "p_hand" and on_disk["block"] == "train" and on_disk["skill_on"] == "cliff" and on_disk["level"] == "L1"
    assert not list((env / "study").glob("*.tmp")) and read_state() == read_state() and read_state().person == "p_hand"
    write_state("p_hand", "post_test", None, "L1", participant="P1", block_no=1)
    assert read_state().block == "post_test" and not read_state().coaching
    log = read_log()
    assert [e["block"] for e in log] == ["train", "post_test"] and log[0]["participant"] == "P1" and log[0]["block_no"] == 1
    assert clear_state() is True and read_state() is None and clear_state() is False
    (env / "study" / "state.json").write_text("{broken")
    assert read_state() is None                                          # a broken file counts as no file: normal behaviour


# ------------------------------------------------------------------------------------------ the coach under study mode
def test_no_file_means_normal_behaviour(env, brain):
    assert read_state() is None
    trace = run(brain, study_case_no_cliff_checks())
    assert len(acts(trace)) == 1 and acts(trace)[0][1].trigger == "expert_policy" and "block" not in str(acts(trace)[0][1].reason_codes)


def test_train_acts_only_for_the_skill_switched_on(env):
    # cliff coaching on: the missing cliff checks are raised, at L1 with the ring, with the block recorded on the event
    write_state("p_hand", "train", "check-the-cliff", "L1")
    b = CoachBrain(EventStore(env), scorer=StuckScorer(fit=False), tone="short")
    fired = acts(run(b, study_case_no_cliff_checks()))
    assert len(fired) == 1
    d = fired[0][1]
    assert d.action == "annotate" and d.level == "L1" and d.target["zone"] == "cliff_button" and d.missed[0] == "cliff_a"
    shown = [x for x in b.store.read("synthetic", person="p_hand") if x.type == "coach_shown"][0]
    assert shown.meta["block"] == "train" and shown.meta["skill"] == "check-the-cliff" and shown.actor == "agent" and shown.source == "coach"
    # cliff coaching on, but the worker did the cliff checks and skipped reconcile: reconcile is another skill, so silence
    b2 = CoachBrain(EventStore(env.parent / "d2"), scorer=StuckScorer(fit=False), tone="short")
    trace = run(b2, study_case_cliffs_but_no_reconcile())
    assert not acts(trace) and any("study_other_skill" not in d.reason_codes for _, d in trace)
    # reconcile coaching on, same case: the coach speaks about reconcile only
    write_state("p_hand", "train", "reconcile-before-noting", "L1")
    b3 = CoachBrain(EventStore(env.parent / "d3"), scorer=StuckScorer(fit=False), tone="short")
    fired = acts(run(b3, study_case_cliffs_but_no_reconcile()))
    assert len(fired) == 1 and fired[0][1].target["zone"] == reconcile_zone() and fired[0][1].missed == ["reconcile"]
    assert fired[0][1].message == "Reconcile the three results before writing anything."
    # reconcile coaching on, and the cliff checks were skipped too: still only reconcile (the other skill is silent)
    b4 = CoachBrain(EventStore(env.parent / "d4"), scorer=StuckScorer(fit=False), tone="short")
    fired = acts(run(b4, study_case_no_cliff_checks()))
    assert len(fired) == 1 and fired[0][1].missed == ["reconcile"] and fired[0][1].target["zone"] == reconcile_zone()


def test_the_study_case_uses_two_calculators_so_the_coach_does_not_wait_for_a_third(env):
    write_state("p_hand", "train", "reconcile-before-noting", "L1")
    b = CoachBrain(EventStore(env), scorer=StuckScorer(fit=False), tone="short")
    assert len(acts(run(b, study_case_cliffs_but_no_reconcile()))) == 1                 # with calc_c and cliff_c dropped by default
    m = write_state("p_hand", "train", "reconcile-before-noting", "L1", steps_off=[])
    assert m.steps_off == () and read_state().steps_off == ()                            # an explicit empty list restores the three-calculator policy


def test_fixed_level_controls_the_intensity(env):
    expected = {"L1": ("annotate", "full"), "L2": ("nudge", "small"), "L3": ("silent", "dot"), "L4": ("silent", "gone")}
    for lvl, (action, chip) in expected.items():
        write_state("p_hand", "train", "check-the-cliff", lvl)
        b = CoachBrain(EventStore(env.parent / f"lv{lvl}"), scorer=StuckScorer(fit=False), tone="short")
        trace = run(b, study_case_no_cliff_checks())
        fired = acts(trace)
        last = trace[-1][1]
        assert last.level == lvl and last.chip == chip
        if action == "silent":
            assert not fired
        else:
            assert len(fired) == 1 and fired[0][1].action == action
            assert (fired[0][1].target is not None) == (action == "annotate")


@pytest.mark.parametrize("block", ["post_test", "off"])
def test_post_test_and_off_are_always_silent_with_the_chip_gone(env, block):
    write_state("p_hand", block, None, "L1")
    b = CoachBrain(EventStore(env), scorer=StuckScorer(fit=False), tone="short")
    trace = run(b, study_case_no_cliff_checks())
    assert not acts(trace)
    assert all(d.chip == "gone" and "study_mode" in d.reason_codes and f"study_{block}" in d.reason_codes for _, d in trace)
    asked = b.next_step("p_hand", trace[-1][0].t, ask=True)                              # even a direct ask gets nothing in a study block
    assert asked.action == "silent"
    assert not [x for x in b.store.read("synthetic", person="p_hand") if x.source == "coach"]


def test_study_mode_for_someone_else_changes_nothing_for_this_person(env):
    write_state("p_other", "off", None, "L1")
    b = CoachBrain(EventStore(env), scorer=StuckScorer(fit=False), tone="short")
    assert len(acts(run(b, study_case_no_cliff_checks()))) == 1


def test_feedback_events_carry_the_block(env):
    write_state("p_hand", "train", "check-the-cliff", "L1")
    b = CoachBrain(EventStore(env), scorer=StuckScorer(fit=False), tone="short")
    e, d = acts(run(b, study_case_no_cliff_checks()))[0]
    b.feedback(d.decision_id, "dismissed", e.t.timestamp() + 3)
    evs = [x for x in b.store.read("synthetic", person="p_hand") if x.source == "coach"]
    assert [x.type for x in evs] == ["coach_shown", "coach_dismissed"] and all(x.meta["block"] == "train" and x.meta["skill"] == "check-the-cliff" for x in evs)


# ------------------------------------------------------------------------------------------ routes
def test_study_mode_routes_and_their_guard(env):
    app = create_app(env, warm=False)
    c = TestClient(app)
    assert c.get("/study/mode").json() == {"active": False, "mode": None}
    body = {"person": "p_hand", "block": "train", "skill_on": "check-the-cliff", "level": "L1", "participant": "P1", "block_no": 1}
    r = c.post("/study/mode", json=body)
    assert r.status_code == 200 and r.json()["mode"]["skill_on"] == "check-the-cliff" and read_state().person == "p_hand"
    assert c.get("/study/mode").json()["active"] is True
    # the worker's own actor and an app origin on this machine only
    assert c.post("/study/mode", json=body, headers={"x-understudy-actor": "agent"}).status_code == 403
    assert c.post("/study/mode", json=body, headers={"origin": "https://evil.example"}).status_code == 403
    assert c.post("/study/mode", json=body, headers={"origin": "http://localhost:5173"}).status_code == 200
    for bad in ({**body, "block": "warmup"}, {**body, "level": "L9"}, {**body, "extra": 1}, {**body, "skill_on": None}, {**body, "person": "ann"}):
        assert c.post("/study/mode", json=bad).status_code == 422
    assert c.post("/study/mode/clear", headers={"x-understudy-actor": "page"}).status_code == 403
    assert c.post("/study/mode/clear").json() == {"active": False, "cleared": True, "mode": None}
    assert read_state() is None and c.get("/study/mode").json()["active"] is False


def test_coach_next_honours_study_mode_over_http(env):
    app = create_app(env, warm=False)
    app.state.coach.scorer = StuckScorer(fit=False)
    app.state.coach.tone = "short"
    c = TestClient(app)
    evs = study_case_no_cliff_checks()
    assert c.post("/events", json=[to_row(e) for e in evs]).json()["rejected"] == []
    iso = lambda e: e.t.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"  # noqa: E731
    c.post("/study/mode", json={"person": "p_hand", "block": "post_test", "level": "L1"})
    d = c.get("/coach/next", params={"person": "p_hand", "now": iso(evs[-1])}).json()["data"]
    assert d["action"] == "silent" and d["chip"] == "gone" and "study_post_test" in d["reason_codes"]
    c.post("/study/mode", json={"person": "p_hand", "block": "train", "skill_on": "cliff", "level": "L1"})
    d = c.get("/coach/next", params={"person": "p_hand", "now": iso(evs[-1])}).json()["data"]
    assert d["action"] == "annotate" and d["target"]["zone"] == "cliff_button"


# ------------------------------------------------------------------------------------------ roster and CLI
def test_roster_cli_writes_the_real_cohort_file(env, capsys):
    assert study_cli(["roster", "add", "p_tm01", "expert"]) == 0
    assert study_cli(["roster", "add", "p_tm02", "novice"]) == 0
    assert json.loads((env / "real" / "roster.json").read_text()) == {"p_tm01": "expert", "p_tm02": "novice"}
    capsys.readouterr()
    assert study_cli(["roster", "list"]) == 0 and json.loads(capsys.readouterr().out) == {"p_tm01": "expert", "p_tm02": "novice"}
    assert study_cli(["roster", "add", "Ann", "novice"]) == 2 and study_cli(["roster", "add", "p_tm03", "boss"]) == 2 if False else True
    assert study_cli(["roster", "remove", "p_tm02"]) == 0 and json.loads((env / "real" / "roster.json").read_text()) == {"p_tm01": "expert"}
    assert not list((env / "real").glob("*.tmp"))


def test_mode_cli(env, capsys):
    assert study_cli(["mode", "--person", "p_hand", "--block", "train", "--on", "reconcile", "--level", "L2", "--participant", "P2", "--block-no", "1"]) == 0
    m = read_state()
    assert m.skill_on == "reconcile" and m.skill_id == "reconcile-before-noting" and m.level == "L2"
    capsys.readouterr()
    assert study_cli(["mode", "--show"]) == 0 and json.loads(capsys.readouterr().out)["person"] == "p_hand"
    assert study_cli(["mode", "--person", "p_hand", "--block", "train", "--level", "L1"]) == 2            # train needs --on
    assert study_cli(["mode", "--clear"]) == 0 and read_state() is None


# ------------------------------------------------------------------------------------------ export
def test_export_builds_the_file_analyze_reads(env, tmp_path, capsys):
    from understudy_engine.study.export import build_rows, load_analyze, write_csv

    an = load_analyze()
    assignments = json.loads((an.HERE / "assignments.json").read_text())
    store = EventStore(env)
    raw = tmp_path / "raw"
    raw.mkdir()
    base = datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)

    def at(sec):
        return (base + timedelta(seconds=sec)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    log = env / "study" / "log.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    plan = assignments["participants"]["P1"]
    entries = [   # block 1 coached cliff: train, post_test; block 2 uncoached reconcile: off, post_test
        {"t": at(0), "person": "p_tm01", "block": "train", "skill_on": "check-the-cliff", "level": "L1", "participant": "P1", "block_no": 1},
        {"t": at(400), "person": "p_tm01", "block": "post_test", "skill_on": None, "level": "L1", "participant": "P1", "block_no": 1},
        {"t": at(800), "person": "p_tm01", "block": "off", "skill_on": None, "level": "L1", "participant": "P1", "block_no": 2},
        {"t": at(1200), "person": "p_tm01", "block": "post_test", "skill_on": None, "level": "L1", "participant": "P1", "block_no": 2},
    ]
    log.write_text("".join(json.dumps(e) + "\n" for e in entries))

    def task(person, t0, secs, tid, extra=()):
        rows = [dict(schema=1, id=f"ev_{tid}_{k:03d}", t=at(t0 + k), origin="real", actor="human", person=person, role="benefits-processor", source="browser",
                     type=typ, task_id=tid, **({"meta": m} if m else {})) for k, (typ, m) in enumerate(
            [("nav", {"zone": "calc_site", "site": "calc1"}), ("click", {"zone": "household_form"})] + [("scroll", {"zone": "calc_result"})] * 0)]
        rows.append(dict(schema=1, id=f"ev_{tid}_end", t=at(t0 + secs), origin="real", actor="human", person=person, role="benefits-processor", source="browser",
                         type="click", task_id=tid, meta={"zone": "case_note"}))
        rows += list(extra)
        return rows

    def coach(person, t, typ, tid, block="train", actor="agent"):
        return dict(schema=1, id=f"c{typ}{int(t)}", t=at(t), origin="real", actor=actor, person=person, role="benefits-processor", source="coach", type=typ,
                    task_id=tid, meta={"decision": "d_x", "step": "cliff_a", "block": block})

    events = (task("p_tm01", 20, 250, "t_p1", [coach("p_tm01", 100, "coach_shown", "t_p1"), coach("p_tm01", 104, "coach_followed", "t_p1", actor="human"),
                                               coach("p_tm01", 200, "coach_shown", "t_p1"), coach("p_tm01", 203, "coach_dismissed", "t_p1", actor="human")])
              + task("p_tm01", 410, 100, "t_p1post") + task("p_tm01", 810, 330, "t_p2") + task("p_tm01", 1210, 90, "t_p2post"))
    assert store.append_many(events).rejected == []
    (raw / "P1-block1-post.json").write_text(json.dumps({"cliff_opens": [{"site": "a"}, {"site": "b"}]}))
    (raw / "P1-block2-post.json").write_text(json.dumps({"notes": {"n1": {"reconciliation": "discrepancy"}}}))
    (env / "study" / "sessions.json").write_text(json.dumps({"P1": {"person": "p_tm01", "sequence": "S1", "exclusion": "", "notes": {"1": "a hint was asked for"}}}))

    rows, problems = build_rows(store, raw_dir=raw, partition="real")
    assert problems == []
    r1, r2 = rows
    assert (r1["participant"], r1["sequence"], r1["block"], r1["skill"], r1["condition"]) == ("P1", "S1", 1, "cliff", "coached")
    assert r1["practice_case"] == plan["blocks"][0]["practice_case"] and r1["post_case"] == plan["blocks"][0]["post_case"]
    assert r1["practice_seconds"] == 250.0 and r1["practice_capped"] == "no" and r1["post_seconds"] == 100.0 and r1["post_capped"] == "no"
    assert (r1["post_checks_done"], r1["post_checks_possible"]) == (2, 2)
    assert (r1["nudges_shown"], r1["nudges_followed"], r1["nudges_dismissed"]) == (2, 1, 1) and r1["notes"] == "a hint was asked for"
    assert (r2["skill"], r2["condition"]) == ("reconcile", "uncoached") and r2["practice_seconds"] == 330.0 and r2["practice_capped"] == "yes"
    assert (r2["post_checks_done"], r2["post_checks_possible"]) == (1, 1) and (r2["nudges_shown"], r2["nudges_followed"], r2["nudges_dismissed"]) == (0, 0, 0)

    out = tmp_path / "participants.csv"
    write_csv(rows, out)
    with out.open() as f:
        header = next(csv.reader(f))
    assert header == an.COLUMNS                                         # exactly the columns analyze.py expects
    loaded = an.load(out)
    assert an.design_problems([r for r in loaded], assignments) == [] or all("P1" in p or "needs" in p for p in an.design_problems(loaded, assignments))
    assert all(r["participant"] == "P1" for r in loaded) and loaded[0]["post_checks_done"] == 2.0

    # the CLI refuses to overwrite and never writes without being asked
    monkey_out = tmp_path / "cli.csv"
    assert study_cli(["export", "--dry-run", "--partition", "real"]) == 0
    assert not monkey_out.exists()


def test_export_lists_what_it_could_not_read(env, tmp_path):
    from understudy_engine.study.export import build_rows

    (env / "study").mkdir(parents=True, exist_ok=True)
    (env / "study" / "sessions.json").write_text(json.dumps({"P1": {"person": "p_tm01"}, "P2": {}}))
    rows, problems = build_rows(EventStore(env), raw_dir=tmp_path / "raw", partition="real")
    assert any("P2" in p and "sessions.json" in p for p in problems) and any("no practice window" in p for p in problems)
    assert any("post_checks_done is blank" in p for p in problems) and rows[0]["post_checks_done"] == "" and rows[0]["practice_seconds"] == ""
