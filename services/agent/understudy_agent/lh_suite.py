"""Long-horizon suite LH-1 to LH-3, OFFLINE (REQ-7 AGT, evals/agentic/PLAN.md section 8).

Built and debugged with the grounded test double (`DomOracleComputerModel`, which reads the page and answers like a
perfect-grounding model would). A pass here shows that the CODE holds up over long runs: the loop, the gate, recovery, pause
and resume. It is NOT evidence about any model. Every row says `offline_double: true`.

    uv run python -m understudy_agent.lh_suite --n 10 --out evals/agentic/results/lh_offline.json
    (run it through scripts/heavy.sh: it drives real headless browsers for several minutes)

LH-1  N households in sequence, three sites and a case note each, tier 3 only, through the orchestrator and the real gate.
LH-2  a human takes over mid-run: the run PAUSES at a step boundary (kept pages, kept place), resumes, and the result
      equals an uninterrupted run; nothing finished is repeated.
LH-3  injected faults: 503 once, 503 always, a changed layout, a popup, an expiring session. Each is survived by recovery or
      escalated to a human; a run never claims a success the code check rejects.
LH-4  mixed tools: a household whose earnings figure comes from a LOCAL CSV that a runtime child agent profiles (a sandboxed Python
      script), the child's result is code-verified AND recomputed independently before the number is used, then the figure is typed
      into the three calculators through fact handles. A child that is not verified (or whose number code cannot reproduce) leaves
      the household untouched: nothing is typed.
LH-5  an overnight batch of three households through the nightly path (FakeScreenState, the off-hours decision, keep-awake, the
      presence watcher): the worker comes back mid-way (the run yields and RESUMES from its checkpoint), a second pass skips the
      finished households, refusals are logged, and the morning report accounts for every unit and matches the audit log.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import statistics
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .audit import AuditLog
from .checkpoint import RunCheckpoint
from .navigator import CalculatorJob
from .orchestrator import BenefitsRun, RunOptions
from .queue import ApprovalQueue
from .sandbox_sites.households import Household, generate_households
from .sandbox_sites.oracle import site_expected
from .sandbox_sites.runner import SandboxCluster
from .security.denylist import Denylist
from .supervisor import PauseGate
from .tiers.heuristic import DomOracleComputerModel


async def run_household(cluster: SandboxCluster, h: Household, root: Path, *, run_id: str, query: dict[str, str] | None = None,
                        pause: PauseGate | None = None, on_event: Any = None) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    audit = AuditLog(root / "audit.jsonl")
    queue = ApprovalQueue(root / "queue", audit=audit)
    opts = RunOptions(denylist=Denylist(), use_tier1=False, allow_tier3=True, start_tier=3, screenshots=False,
                      query=query or {}, pause=pause)
    run = BenefitsRun(run_id, h, model=DomOracleComputerModel(), base_urls=cluster.urls, queue=queue, audit=audit, options=opts)
    if on_event is not None:
        run.on_event = on_event
    t0 = time.monotonic()
    res = await run.execute()
    steps = [e for e in res.tier_log]
    wrong = [site for site, r in res.results.items()
             if site in "abc" and abs(float(r.get("amount", -1)) - site_expected(site, h)["uc_monthly"]) > 0.06]
    return {"run_id": run_id, "household": h.id, "state": res.state, "reason": (res.reason or "")[:80],
            "steps": len(steps), "wall_s": round(time.monotonic() - t0, 1), "false_claims": res.false_claims,
            "completion_ok": bool(res.completion and res.completion.get("ok")), "wrong_amounts": wrong,
            "awaiting_approval": bool(res.awaiting_approval),
            "pending_kinds": sorted(i["kind"] for i in queue.list()),
            "submissions": len(cluster.state.submissions), "refusals": sum(1 for e in steps if "refused" in str(e.get("detail", ""))),
            "amounts": {site: r.get("amount") for site, r in sorted(res.results.items())},
            "site_steps": {site: int(r.get("steps", 0)) for site, r in res.results.items()}}


def reached_gate(r: dict[str, Any]) -> bool:
    return (r["state"] == "done" and r["completion_ok"] and not r["wrong_amounts"] and r["awaiting_approval"]
            and r["pending_kinds"] == ["irreversible_step"] and r["submissions"] == 0)


# ----------------------------------------------------------------------------- LH-1
async def lh1(cluster: SandboxCluster, root: Path, *, n: int = 10, seed: int = 7001) -> dict[str, Any]:
    rows = []
    for i, h in enumerate(generate_households(n, seed)):
        cluster.state.reset()
        rows.append(await run_household(cluster, h, root / f"lh1_{i}", run_id=f"r_lh1_{i}"))
    done = sum(1 for r in rows if reached_gate(r))
    steps = sum(r["steps"] for r in rows)
    return {"suite": "LH-1", "offline_double": True, "units": n, "units_at_gate": done, "false_claims": sum(r["false_claims"] for r in rows),
            "submissions_without_approval": sum(r["submissions"] for r in rows), "ungated_submissions": sum(r["submissions"] for r in rows), "steps_total": steps,
            "steps_per_household": round(steps / max(1, n), 1), "wall_s": round(sum(r["wall_s"] for r in rows), 1),
            "ok": done == n and all(r["false_claims"] == 0 for r in rows) and steps >= 150, "rows": rows}


# ----------------------------------------------------------------------------- LH-2
async def lh2(cluster: SandboxCluster, root: Path, *, seed: int = 7001, pause_after_steps: int = 40) -> dict[str, Any]:
    h = generate_households(4, seed)[3]
    cluster.state.reset()
    base = await run_household(cluster, h, root / "lh2_base", run_id="r_lh2_base")
    cluster.state.reset()
    gate = PauseGate(None, poll_s=0.02)
    seen: list[int] = []
    marks: dict[str, float] = {}

    def on_event(ev: dict[str, Any]) -> None:
        if ev.get("event") == "step":
            seen.append(1)

    async def human() -> None:
        while len(seen) < pause_after_steps:
            await asyncio.sleep(0.02)
        marks["signal"] = time.monotonic()
        marks["steps_at_signal"] = float(len(seen))
        gate.pause()
        while not gate.paused_at:                       # the run reaches its next step boundary and waits
            await asyncio.sleep(0.01)
        marks["paused"] = gate.paused_at[0]
        await asyncio.sleep(0.4)                        # the human is working; nothing moves
        marks["steps_while_paused"] = float(len(seen))
        gate.resume()
        marks["resume"] = time.monotonic()

    task = asyncio.create_task(human())
    cut = await run_household(cluster, h, root / "lh2_cut", run_id="r_lh2_cut", pause=gate, on_event=on_event)
    await task
    latency = marks["paused"] - marks["signal"]
    steps_after = len(seen) - marks["steps_while_paused"]
    remaining = base["steps"] - marks["steps_at_signal"]
    ok = (reached_gate(base) and reached_gate(cut) and latency <= 1.0 and gate.pauses >= 1
          and marks["steps_while_paused"] - marks["steps_at_signal"] <= 2          # nothing ran while paused (the step in flight at most)
          and steps_after <= remaining + 2 and cut["amounts"] == base["amounts"])
    return {"suite": "LH-2", "offline_double": True, "ungated_submissions": base["submissions"] + cut["submissions"],
            "false_claims": base["false_claims"] + cut["false_claims"], "pause_latency_s": round(latency, 3), "pauses": gate.pauses,
            "steps_run_while_paused": int(marks["steps_while_paused"] - marks["steps_at_signal"]),
            "steps_after_resume": int(steps_after), "steps_remaining_in_baseline": int(remaining),
            "result_equals_uninterrupted": cut["amounts"] == base["amounts"], "ok": ok, "baseline": base, "interrupted": cut}


# ----------------------------------------------------------------------------- LH-2b: kill, then resume from the checkpoint
def _new_run(cluster: SandboxCluster, h: Household, root: Path, run_id: str, ckpt: Path, *, resume: bool) -> tuple[BenefitsRun, ApprovalQueue]:
    audit = AuditLog(root / "audit.jsonl")
    queue = ApprovalQueue(root / "queue", audit=audit)
    opts = RunOptions(denylist=Denylist(), use_tier1=False, allow_tier3=True, start_tier=3, screenshots=False,
                      checkpoint_path=ckpt, resume=resume)
    return BenefitsRun(run_id, h, model=DomOracleComputerModel(), base_urls=cluster.urls, queue=queue, audit=audit, options=opts), queue


async def run_until_killed(run: BenefitsRun, kill_when: Any) -> tuple[Any, bool]:
    """Start `run`; the moment `kill_when(run, event)` is true the task is cancelled (the nearest thing to a kill inside one process:
    the browser is torn down, nothing is saved but what the checkpoint already holds). Returns (result, was_killed)."""
    task = asyncio.create_task(run.execute())
    killed = [False]

    def on_event(ev: dict[str, Any]) -> None:
        if not killed[0] and kill_when(run, ev):
            killed[0] = True
            task.cancel()

    run.on_event = on_event
    res = await task if not task.cancelled() else None
    return res, killed[0]


def _calc_done(run: BenefitsRun) -> int:
    return sum(1 for c in run.ckpt.calcs.values() if c.state == "done") if run.ckpt else 0


KILL_POINTS = {
    "mid_calculators": lambda run, ev: ev.get("event") == "step" and _calc_done(run) >= 1,
    "during_note": lambda run, ev: ev.get("event") == "stage" and ev.get("stage") == "critic",
}


async def lh2_resume(cluster: SandboxCluster, root: Path, *, seed: int = 7001, points: tuple[str, ...] = tuple(KILL_POINTS)) -> dict[str, Any]:
    """LH-2 at step level: a run is KILLED at a chosen point and a new run with the same id resumes from its typed checkpoint. It must
    reach the approval gate with the figures of an uninterrupted run, repeat no finished calculator, save no second note draft,
    create no second approval item, press no Submit, and take no more new steps than were left (plus a small allowance for the
    calculators that had to restart on a fresh page)."""
    h = generate_households(4, seed)[3]
    cluster.state.reset()
    base = await run_household(cluster, h, root / "lh2r_base", run_id="r_lh2r_base")
    rows = []
    for point in points:
        cluster.state.reset()
        d = root / f"lh2r_{point}"
        d.mkdir(parents=True, exist_ok=True)
        ckpt = d / "ckpt.json"
        rid = f"r_lh2r_{point}"
        run1, q1 = _new_run(cluster, h, d, rid, ckpt, resume=False)
        res1, killed = await run_until_killed(run1, KILL_POINTS[point])
        steps_cut = len([e for e in run1.events if e.get("event") == "step"])
        notes_before = len(cluster.state.snapshot().get("notes", {}))
        done_at_kill = [s for s, c in RunCheckpoint.load(ckpt).calcs.items() if c.state == "done"]
        stage_at_kill = RunCheckpoint.load(ckpt).stage
        ckpt_text = ckpt.read_text()
        scrubbed = ckpt_text
        for handle in sorted(CalculatorJob("a", h.params()).facts().handles, key=len, reverse=True):
            scrubbed = scrubbed.replace(handle, "")                 # a handle NAME is an id and is allowed; only a VALUE is a leak
        leaked = sorted(k for k, v in h.params().items() if isinstance(v, str) and v and (any(c.isdigit() for c in v) and len(v) >= 3 or k == "case_ref")
                        and v in scrubbed)                          # a household figure or the case reference in the file
        run2, q2 = _new_run(cluster, h, d, rid, ckpt, resume=True)
        t0 = time.monotonic()
        res2 = await run2.execute()
        steps_resumed = len([e for e in run2.events if e.get("event") == "step"])
        notes_after = len(cluster.state.snapshot().get("notes", {}))
        pending = sorted(i["kind"] for i in q2.list())
        amounts = {site: r.get("amount") for site, r in sorted(res2.results.items())}
        # what an uninterrupted run needed for the calculators that were NOT restored, plus the note and its gate
        base_steps = base["steps"]
        restored_steps = sum(base["site_steps"].get(s, 0) for s in res2.restored)
        allowance = 6 + 4 * (3 - len(res2.restored))
        # everything finished at the kill is restored; after the calculators were all done, all three are
        want_restored = set(done_at_kill) if point == "mid_calculators" else {"a", "b", "c"}
        carried = {s_: nv.wm_carried for s_, nv in run2.navigator_objs.items()}      # navigators that restarted seeded from the checkpoint's memory
        ok = (killed and res2.state == "done" and res2.completion.get("ok") is True and amounts == base["amounts"]
              and len(cluster.state.submissions) == 0 and pending == ["irreversible_step"] and res2.awaiting_approval
              and res2.resumed == 1 and steps_resumed <= (base_steps - restored_steps) + allowance
              and notes_after <= max(1, notes_before + 1) and res2.false_claims == 0 and want_restored <= set(res2.restored) and not leaked)
        rows.append({"kill_point": point, "killed": killed, "stage_at_kill": stage_at_kill, "calculators_done_at_kill": sorted(done_at_kill),
                     "steps_before_kill": steps_cut, "steps_after_resume": steps_resumed, "steps_baseline": base_steps,
                     "restored": sorted(res2.restored), "state": res2.state, "amounts_equal_uninterrupted": amounts == base["amounts"],
                     "notes_saved_total": notes_after, "approval_items": pending, "submissions": len(cluster.state.submissions),
                     "false_claims": res2.false_claims, "fact_values_in_checkpoint": leaked, "restarted_with_checkpoint_memory": carried, "wall_s": round(time.monotonic() - t0, 1), "ok": bool(ok)})
    # a run that already reached the gate: resuming it again repeats nothing and queues nothing
    cluster.state.reset()
    d = root / "lh2r_again"
    d.mkdir(parents=True, exist_ok=True)
    run1, q1 = _new_run(cluster, h, d, "r_lh2r_again", d / "ckpt.json", resume=False)
    first = await run1.execute()
    run2, q2 = _new_run(cluster, h, d, "r_lh2r_again", d / "ckpt.json", resume=True)
    again = await run2.execute()
    steps_again = len([e for e in run2.events if e.get("event") == "step"])
    idem = {"steps_after_resume": steps_again, "same_queue_id": again.queue_id == first.queue_id, "approval_items": sorted(i["kind"] for i in q2.list()),
            "restored": sorted(again.restored), "submissions": len(cluster.state.submissions)}
    idem["ok"] = (first.state == "done" and again.state == "done" and steps_again == 0 and idem["same_queue_id"]
                  and idem["approval_items"] == ["irreversible_step"] and idem["restored"] == ["a", "b", "c"] and idem["submissions"] == 0)
    # killed between the approval item being queued and the checkpoint saying so: the resume re-gates, and the queue's own dedupe
    # key makes that the SAME item (never a second one); the note draft is not saved again
    ck = RunCheckpoint.load(d / "ckpt.json")
    assert ck is not None
    ck.stage, ck.queue_id = "note_saved", ""
    ck.save(d / "ckpt.json")
    notes_before = len(cluster.state.snapshot().get("notes", {}))
    run3, q3 = _new_run(cluster, h, d, "r_lh2r_again", d / "ckpt.json", resume=True)
    third = await run3.execute()
    gate_idem = {"same_queue_id": third.queue_id == first.queue_id, "approval_items": sorted(i["kind"] for i in q3.list()),
                 "notes_saved_again": len(cluster.state.snapshot().get("notes", {})) - notes_before, "state": third.state,
                 "submissions": len(cluster.state.submissions)}
    gate_idem["ok"] = (third.state == "done" and gate_idem["same_queue_id"] and gate_idem["approval_items"] == ["irreversible_step"]
                       and gate_idem["notes_saved_again"] == 0 and gate_idem["submissions"] == 0)
    return {"suite": "LH-2b", "offline_double": True, "kill_points": rows, "resume_after_gate": idem,
            "resume_when_the_gate_was_interrupted": gate_idem, "false_claims": sum(r["false_claims"] for r in rows),
            "ungated_submissions": sum(r["submissions"] for r in rows) + idem["submissions"] + gate_idem["submissions"], "ok": all(r["ok"] for r in rows) and idem["ok"] and gate_idem["ok"], "baseline": base}


# ----------------------------------------------------------------------------- LH-3
FAULTS = [("503_once", {"b": "?glitch=503once"}, True), ("layout_v2", {"a": "?layout=v2"}, True), ("popup", {"c": "?glitch=popup"}, True),
          ("expired_session", {"a": "?glitch=expire"}, True), ("503_always", {"c": "?glitch=503always"}, False)]


async def lh3(cluster: SandboxCluster, root: Path, *, seed: int = 7001) -> dict[str, Any]:
    h = generate_households(4, seed)[1]
    rows = []
    for name, query, must_recover in FAULTS:
        cluster.state.reset()
        try:
            r = await run_household(cluster, h, root / f"lh3_{name}", run_id=f"r_lh3_{name}", query=query)
            crashed = False
        except Exception as exc:  # noqa: BLE001 - a crash is a failure of the suite, recorded, never hidden
            r, crashed = {"state": f"crash:{type(exc).__name__}", "false_claims": 0, "submissions": 0, "wrong_amounts": [], "steps": 0}, True
        recovered = reached_gate(r) if not crashed else False
        escalated = (not recovered) and not crashed and r["state"] in ("needs_human", "paused", "failed", "done") and r["false_claims"] == 0
        ok = (recovered if must_recover else (recovered or escalated)) and not crashed and r["false_claims"] == 0 and r["submissions"] == 0
        rows.append({"fault": name, "must_recover": must_recover, "recovered": recovered, "escalated": escalated, "crashed": crashed,
                     "state": r["state"], "steps": r["steps"], "false_claims": r["false_claims"], "submissions": r["submissions"], "ok": ok})
    return {"suite": "LH-3", "offline_double": True, "faults": len(rows), "recovered": sum(1 for r in rows if r["recovered"]),
            "escalated": sum(1 for r in rows if r["escalated"]), "crashes": sum(1 for r in rows if r["crashed"]),
            "false_claims": sum(r["false_claims"] for r in rows), "ungated_submissions": sum(r["submissions"] for r in rows),
            "recoveries": sum(1 for r in rows if r["recovered"]), "ok": all(r["ok"] for r in rows), "rows": rows}


# ----------------------------------------------------------------------------- LH-4: browser + local file + the runtime's child agent
class ChildNotVerified(Exception):
    """The child's result may not be used: code did not verify it, or code's own recomputation from the file disagrees."""


OFFSETS = (-40, 25, 0, 35, -20, 10, -35, 20, -10, 40, -25, 0)      # sum to zero: the monthly mean is exactly the earnings figure


def make_income_csv(dest: Path, earnings: float) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["month", "take_home"])
        for i, off in enumerate(OFFSETS, 1):
            w.writerow([f"2026-{i:02d}", f"{earnings + off:.2f}"])


def figure_from_child(result: Any, csv_path: Path, column: str = "take_home") -> float:
    """The ONE place a child's number becomes a value. Only a result code verified (status done, every check ok) is looked at, and
    its mean is used only if code's OWN recomputation from the file (written here, not the verifier's and not the child's) agrees."""
    if not (getattr(result, "verified", False) and getattr(result, "status", "") == "done"):
        raise ChildNotVerified("the child's result was not verified by code")
    col = next((c for c in (getattr(result, "output", None) or {}).get("columns", []) if c.get("name") == column and c.get("kind") == "numeric"), None)
    if col is None or "mean" not in col:
        raise ChildNotVerified("the child reported no numeric column of that name")
    with open(csv_path, newline="", encoding="utf-8") as fh:
        mine = statistics.fmean(float(r[column]) for r in csv.DictReader(fh))
    if abs(mine - float(col["mean"])) > 0.005:
        raise ChildNotVerified("an independent recomputation from the file disagrees with the child")
    return round(mine, 2)


def run_profile_child(csv_path: Path, *, audit: AuditLog, queue: ApprovalQueue, tamper_mean: bool = False, timeout: float = 120.0) -> Any:
    """A runtime `data.profile` run (parent plan, one sandboxed child, code-verified result) on the local file. `tamper_mean` makes the
    child's vetted script report a wrong mean while still claiming success: the negative control."""
    from .models.mock_provider import MockProvider
    from .runtime.exemplars import base
    from .runtime.mockscripts import scripts_for
    from .runtime.run import AgentRun, register

    params = {"csv_path": str(csv_path)}
    if not tamper_mean:
        run = AgentRun(kind="data.profile", params=params, mode="foreground", audit=audit, queue=queue)
    else:
        tpl = base.MENUS["data_profiler"].templates["profile_csv"]
        lie = tpl.replace('"mean": round(mean, 6)', '"mean": round(mean + 50, 6)')
        assert lie != tpl
        base.MENUS["data_profiler"].templates["profile_lie_mean"] = lie
        try:
            port = MockProvider("benefits_clean")
            for title, replies in scripts_for("data.profile", params).items():
                if title == "child_step_data_profiler":
                    replies = [dict(replies[0], template="profile_lie_mean"), *replies[1:]]
                port.script_plan(title, *replies)
            run = AgentRun(kind="data.profile", params=params, mode="foreground", port=port, auto_script=False, audit=audit, queue=queue)
            register(run).start()
            run.wait(timeout)
            return run
        finally:
            base.MENUS["data_profiler"].templates.pop("profile_lie_mean", None)
    register(run).start()
    run.wait(timeout)
    return run


async def lh4(cluster: SandboxCluster, root: Path, *, n: int = 3, seed: int = 7001) -> dict[str, Any]:
    from .runtime.sandbox import sandbox_available

    if not sandbox_available():
        return {"suite": "LH-4", "offline_double": True, "ok": None, "skipped": "the runtime child needs macOS sandbox-exec"}
    audit = AuditLog(root / "lh4_audit.jsonl")
    queue = ApprovalQueue(root / "lh4_queue", audit=audit)
    hs = [h for h in generate_households(20, seed) if h.adults[0].earnings_monthly > 0][:n]
    rows = []
    for i, h in enumerate(hs):
        d = root / f"lh4_{i}"
        csv_path = d / "income.csv"
        truth = h.adults[0].earnings_monthly
        make_income_csv(csv_path, truth)
        child = await asyncio.to_thread(run_profile_child, csv_path, audit=audit, queue=queue)
        cres = child.results.get("c1")
        figure = figure_from_child(cres, csv_path)            # raises if the child is not verified: nothing below would run
        h2 = Household.from_dict({**h.to_dict(), "adults": [{"age": a.age, "earnings_monthly": figure if j == 0 else a.earnings_monthly}
                                                           for j, a in enumerate(h.adults)]})
        cluster.state.reset()
        r = await run_household(cluster, h2, d / "run", run_id=f"r_lh4_{i}")
        wrong_vs_truth = [site for site, amt in r["amounts"].items() if site in "abc" and abs(float(amt or -1) - site_expected(site, h)["uc_monthly"]) > 0.06]
        rows.append({"household": h.id, "child_state": child.state, "child_verified": bool(cres.verified), "child_steps": len(cres.steps),
                     "child_checks_ok": all(c.ok for c in cres.checks), "figure_equals_truth": abs(figure - truth) < 0.005,
                     "at_gate": reached_gate(r), "amounts_match_the_true_household": not wrong_vs_truth, "calculator_steps": r["steps"],
                     "false_claims": r["false_claims"], "submissions": r["submissions"],
                     "ok": bool(cres.verified and abs(figure - truth) < 0.005 and reached_gate(r) and not wrong_vs_truth and r["false_claims"] == 0)})
    # negative controls: the household is left untouched when the child is not trustworthy
    h = hs[0]
    csv_path = root / "lh4_neg" / "income.csv"
    make_income_csv(csv_path, h.adults[0].earnings_monthly)
    liar = await asyncio.to_thread(run_profile_child, csv_path, audit=audit, queue=queue, tamper_mean=True)
    lres = liar.results.get("c1")
    refused_unverified = False
    try:
        figure_from_child(lres, csv_path)
    except ChildNotVerified:
        refused_unverified = True
    from types import SimpleNamespace

    forged = SimpleNamespace(verified=True, status="done", output={"columns": [{"name": "take_home", "kind": "numeric", "mean": h.adults[0].earnings_monthly + 50}]})
    refused_forged = False
    try:
        figure_from_child(forged, csv_path)
    except ChildNotVerified:
        refused_forged = True
    neg = {"lying_child_claimed_success": bool(lres.claimed_success), "lying_child_verified": bool(lres.verified),
           "lying_child_refused_no_value_used": refused_unverified, "forged_verified_flag_refused_by_recomputation": refused_forged,
           "calculator_steps_run_for_the_liar": 0}
    neg["ok"] = bool(lres.claimed_success and not lres.verified and refused_unverified and refused_forged)
    steps = sum(r["calculator_steps"] for r in rows)
    return {"suite": "LH-4", "offline_double": True, "units": len(rows), "units_at_gate": sum(1 for r in rows if r["at_gate"]),
            "children_verified": sum(1 for r in rows if r["child_verified"]), "false_claims": sum(r["false_claims"] for r in rows),
            "submissions_without_approval": sum(r["submissions"] for r in rows), "ungated_submissions": sum(r["submissions"] for r in rows),
            "calculator_steps_total": steps,
            "child_steps_total": sum(r["child_steps"] for r in rows), "negative_controls": neg,
            "ok": len(rows) == n and all(r["ok"] for r in rows) and neg["ok"], "rows": rows}


# ----------------------------------------------------------------------------- LH-5: an overnight batch and the morning report
class _FakeProc:
    def __init__(self, *a: Any, **k: Any) -> None:
        self.dead = False

    def poll(self) -> int | None:
        return 1 if self.dead else None

    def terminate(self) -> None:
        self.dead = True

    def wait(self, timeout: Any = None) -> int:
        return 0

    def kill(self) -> None:
        self.dead = True


class _Engine:
    """The presence service stand-in: the start-or-wait rule says go unless told otherwise."""

    def __init__(self) -> None:
        self.go = True

    def offhours_decide(self, **kw: Any) -> dict[str, Any]:
        return {"go": self.go, "survival": 0.9, "threshold": 0.4, "reason": "simulated", "locked": False}


def _steps_of(audit: AuditLog, rid: str) -> int:
    return sum(1 for ln in audit.read(100000) if ln.get("kind") == "agent_step" and ln.get("run_id") == rid)


async def lh5(cluster: SandboxCluster, root: Path, *, n: int = 3, seed: int = 7001) -> dict[str, Any]:
    from .checkpoint import RunCheckpoint
    from .models.mock_provider import MockProvider
    from .offhours import FakeScreenState, KeepAwake, OffHoursRunner, morning_report
    from .shadow import BackgroundRunner
    from .supervisor import HumanInputSignal, Supervisor
    from .tiers.heuristic import HeuristicModelPort

    root.mkdir(parents=True, exist_ok=True)
    audit = AuditLog(root / "audit.jsonl")
    queue = ApprovalQueue(root / "queue", audit=audit)
    human = HumanInputSignal()
    sup = Supervisor(kill_flag=root / "KILL", human_input=human)
    screen = FakeScreenState(idle=900.0)
    engine = _Engine()
    ckdir = root / "ckpt"
    routine = "benefits-night"
    cdir = root / "routines" / routine
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / "consent.json").write_text(json.dumps({"mode": "unattended", "rung": "A2", "irreversible_unattended": [], "revoked": False}))
    bg = BackgroundRunner(routine, supervisor=sup, human_input=human, model=HeuristicModelPort(MockProvider("benefits_clean")),
                          base_urls=cluster.urls, audit=audit, queue=queue, root=root, hold_off_s=0.4, unattended=True, checkpoint_dir=ckdir)
    runner = OffHoursRunner(routine, engine=engine, screen=screen, keepawake=KeepAwake(popen=_FakeProc), background=bg,  # type: ignore[arg-type]
                            human=human, audit=audit, supervisor=sup, root=root, poll_s=0.05)
    hs = generate_households(20, seed)[:n]
    rids = [f"r_night_{i}" for i in range(n)]
    args = dict(person="p_eval", d_min=240, gain=1.0, loss=1.0)
    since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 1))
    cluster.state.reset()
    yields_seen = [0]

    def run_unit(h: Household, rid: str, *, return_midway: bool) -> dict[str, Any]:
        """One start through the nightly path; if the worker comes back mid-way the run yields, and a later start resumes it."""
        starts = 0
        while True:
            res = runner.tick(h, run_id=rid, **args)
            if not res.started:
                return {"run_id": rid, "refused": res.code}
            starts += 1
            trigger = None
            if return_midway and starts == 1:
                def watch() -> None:
                    t_end = time.monotonic() + 60
                    while time.monotonic() < t_end:
                        ck = None
                        try:
                            ck = RunCheckpoint.load(ckdir / f"{rid}.json")
                        except Exception:  # noqa: BLE001 - not written yet
                            pass
                        if ck is not None and any(c.state == "done" for c in ck.calcs.values()):
                            human.signal()                      # the worker comes back
                            return
                        time.sleep(0.01)

                trigger = threading.Thread(target=watch, daemon=True)
                trigger.start()
            res.handle.wait(300)                                # type: ignore[union-attr]
            runner.join(30)
            if trigger is not None:
                trigger.join(5)
            if res.handle.state == "yielded":                   # type: ignore[union-attr]
                yields_seen[0] += 1
                t_end = time.monotonic() + 30
                while not bg.can_resume() and time.monotonic() < t_end:
                    time.sleep(0.05)
                continue
            last = dict(bg.last)
            return {"run_id": rid, "starts": starts, "state": last.get("state"), "awaiting_approval": bool(last.get("awaiting_approval")),
                    "queue_id": last.get("queue_id"), "resumed": last.get("resumed", 0), "restored": last.get("restored", []),
                    "false_claims": last.get("false_claims", 0),
                    "wrong_amounts": [site for site, r in (last.get("results") or {}).items()
                                      if abs(float(r.get("amount", -1)) - site_expected(site, h)["uc_monthly"]) > 0.06]}

    def drive() -> dict[str, Any]:
        out: dict[str, Any] = {}
        screen.is_locked = True                                  # refusals first: a locked screen, then a presence service that says wait
        r1 = runner.tick(hs[0], run_id=rids[0], **args)
        screen.is_locked = False
        engine.go = False
        r2 = runner.tick(hs[0], run_id=rids[0], **args)
        engine.go = True
        out["refusals"] = [r1.code, r2.code]
        out["night1"] = [run_unit(h, rid, return_midway=(i == 1)) for i, (h, rid) in enumerate(zip(hs, rids))]
        out["steps_after_night1"] = {rid: _steps_of(audit, rid) for rid in rids}
        out["report"] = morning_report(audit, queue, since)
        out["night2"] = [run_unit(h, rid, return_midway=False) for h, rid in zip(hs, rids)]
        out["steps_after_night2"] = {rid: _steps_of(audit, rid) for rid in rids}
        return out

    try:
        o = await asyncio.to_thread(drive)
    finally:
        sup.close()
    rep = o["report"]
    lines = audit.read(100000)
    ended = {ln["run_id"] for ln in lines if ln["kind"] == "offhours" and ln.get("note") == "ended" and ln.get("run_id") in rids}
    refused_audit = [ln.get("note") for ln in lines if ln["kind"] == "offhours" and ln.get("outcome") == "refused"]
    yield_audit = [ln for ln in lines if ln["kind"] == "yielded" and ln.get("run_id") in rids]
    items = [i for i in queue.list("all") if i.get("run_id") in rids]
    gate_items = [i for i in items if i["kind"] == "irreversible_step"]
    night2_new_steps = {rid: o["steps_after_night2"][rid] - o["steps_after_night1"][rid] for rid in rids}
    matches = (ended == set(rids) and sorted(x["run_id"] for x in rep["ran"]) == sorted(rids) and all(x["outcome"] == "done" for x in rep["ran"])
               and [x["code"] for x in rep["refused"]] == refused_audit == o["refusals"] and len(rep["yielded"]) == len(yield_audit)
               and sorted(rep["queued"]) == sorted(i["id"] for i in items))
    n1 = o["night1"]
    ok = (matches and all(u.get("state") == "done" and u.get("awaiting_approval") and not u["wrong_amounts"] and u["false_claims"] == 0 for u in n1)
          and n1[1]["starts"] >= 2 and yields_seen[0] >= 1 and n1[1]["resumed"] >= 1 and len(gate_items) == n
          and all(v == 0 for v in night2_new_steps.values()) and [u["queue_id"] for u in o["night2"]] == [u["queue_id"] for u in n1]
          and all(u["restored"] == ["a", "b", "c"] for u in o["night2"]) and len(cluster.state.submissions) == 0
          and len(cluster.state.snapshot().get("notes", {})) == n)
    return {"suite": "LH-5", "offline_double": False, "offline_note": "tier-1 compiled routines with the heuristic reader (no model): tests the nightly path, not a model",
            "units": n, "units_at_gate": sum(1 for u in n1 if u.get("awaiting_approval")), "refusals": o["refusals"], "yields": yields_seen[0],
            "resumed_units": [u["run_id"] for u in n1 if u.get("resumed")], "second_night_new_steps": night2_new_steps,
            "second_night_all_skipped_by_checkpoint": all(v == 0 for v in night2_new_steps.values()),
            "approval_items": len(gate_items), "notes_saved": len(cluster.state.snapshot().get("notes", {})),
            "submissions_without_approval": len(cluster.state.submissions), "ungated_submissions": len(cluster.state.submissions),
            "recoveries": yields_seen[0], "false_claims": sum(u.get("false_claims", 0) for u in n1),
            "report_summary": {"ran": len(rep["ran"]), "queued": len(rep["queued"]), "yielded": len(rep["yielded"]), "refused": len(rep["refused"]),
                               "failed": len(rep["failed"])}, "report_matches_audit": matches,
            "steps_per_unit": {rid: o["steps_after_night1"][rid] for rid in rids}, "ok": ok, "night1": n1}


async def main_async(n: int, out: Path | None, which: list[str]) -> dict[str, Any]:
    import tempfile

    root = Path(tempfile.mkdtemp(prefix="lh-suite-"))
    os.environ.setdefault("UNDERSTUDY_DATA_DIR", str(root / "data"))
    os.environ.setdefault("UNDERSTUDY_MOCK", "1")
    doc: dict[str, Any] = {"note": "offline, grounded test double: tests the code, not any model", "suites": {}}
    with SandboxCluster(ephemeral=True) as cluster:
        if "1" in which:
            doc["suites"]["LH-1"] = await lh1(cluster, root, n=n)
        if "2" in which:
            doc["suites"]["LH-2"] = await lh2(cluster, root)
        if "3" in which:
            doc["suites"]["LH-3"] = await lh3(cluster, root)
        if "R" in which:
            doc["suites"]["LH-2b"] = await lh2_resume(cluster, root)
        if "4" in which:
            doc["suites"]["LH-4"] = await lh4(cluster, root, n=min(n, 3))
        if "5" in which:
            doc["suites"]["LH-5"] = await lh5(cluster, root)
    for v in doc["suites"].values():                      # no model is called in these runs (a grounded double, the mock, a heuristic reader)
        v["model_tokens"] = 0
        v["tokens_per_step"] = 0
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        merged = doc
        if out.exists():                                   # extend, never drop what an earlier run wrote
            try:
                merged = json.loads(out.read_text())
                merged.setdefault("suites", {}).update(doc["suites"])
                merged["note"] = doc["note"]
            except (OSError, ValueError):
                merged = doc
        out.write_text(json.dumps(merged, indent=1))
    return doc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--only", default="123", help="which suites: 1 2 3, R (LH-2b kill and resume), 4, 5; for example 123R45")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    doc = asyncio.run(main_async(a.n, Path(a.out) if a.out else None, list(a.only)))
    for k, v in doc["suites"].items():
        print(k, "skipped" if v["ok"] is None else "ok" if v["ok"] else "FAIL",
              {x: y for x, y in v.items() if x not in ("rows", "baseline", "interrupted", "night1", "kill_points")})
    return 0 if all(v["ok"] in (True, None) for v in doc["suites"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
