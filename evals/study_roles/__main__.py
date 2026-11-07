"""Command line of the role studies.

    uv run --package understudy-agent python -m evals.study_roles fake --role programmer --plan "1=skipper+obeys,5=expert"    # harness test, NO model, no cost
    uv run --package understudy-agent python -m evals.study_roles experts --role programmer                                  # record the scripted EXPERT runs (no model)
    uv run --package understudy-agent --env-file .env python -m evals.study_roles pilot --role programmer --tier fast         # feasibility pilot (needs GO)
    uv run --package understudy-agent --env-file .env python -m evals.study_roles run --role programmer --tier fast --units 3  # the study (needs GO and a pilot that passed)
    uv run --package understudy-agent python -m evals.study_roles analyze --role programmer                                  # summary.json and REPORT.md

``fake`` and ``experts`` never write to results/. ``pilot`` and ``run`` refuse to start without the file evals/study_roles/GO (created only after the lead has committed PLAN.md
and replied GO with a budget), without a model, and with UNDERSTUDY_MOCK set. Everything written is checked by ``analysis_io.check_output_dir`` (never under evals/study/).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))

from evals.study_roles import analysis_rows  # noqa: E402
from evals.study_roles.design import ParticipantSpec, build_participants, build_pilot  # noqa: E402
from evals.study_roles.roles import ROLE_CFG, cfg, world_port  # noqa: E402
from evals.study_sim import analysis_io as sim_io  # noqa: E402
from evals.study_sim.budget import Budget  # noqa: E402

GO_FILE = HERE / "GO"
RESULTS = HERE / "results"
FAKE_DIR = HERE / "fake_runs"
from evals.study_roles.budget_roles import CAP_USD as BUDGET_CAP_USD, RolesBudget  # noqa: E402   (US$14 for BOTH roles including the pilots: the lead's message of 7 Nov 2026)


def _port_free(port: int) -> bool:
    """Nothing is listening on 127.0.0.1:port (a connect is refused) and it can be bound."""
    import socket

    with socket.socket() as s:
        s.settimeout(0.3)
        if s.connect_ex(("127.0.0.1", port)) == 0:
            return False
    try:
        with socket.socket() as s:
            s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False


def pick_ports(role: str, n: int) -> list[int]:
    """The ports of ``n`` private worlds: the first free ports of the role's block (programmer 7941-7948, analyst 7951-7958: the pack's capture sites name exactly these), so that two
    runs of this harness side by side (a pilot and an expert recording, say) never share a sandbox or reset each other's state."""
    from evals.study_roles.roles import PORT_BASE

    base = PORT_BASE[role]
    free = [p for p in range(base, base + 8) if _port_free(p)]
    if len(free) < n:
        raise SystemExit(f"fewer than {n} free private ports for {role} in {base}-{base + 7}: another run of this harness is using them")
    return free[:n]


def make_worlds(role: str, n: int, outdir: Path | None):
    from evals.study_roles.runner import RoleWorld
    from evals.study_sim.infra import build_extension, snapshot_pipeline

    info = snapshot_pipeline()
    if outdir is not None:
        sim_io.write_provenance(outdir)
        (outdir / "snapshot.json").write_text(json.dumps({k: v for k, v in info.items() if k != "path"}, indent=1))
    print(f"pipeline snapshot {info['fingerprint']} of git {info['git_head'][:8]} (+{info['uncommitted_files_in_snapshot_dirs']} uncommitted files)", flush=True)
    worlds, built = [], []
    ports = pick_ports(role, n)
    for k in range(n):
        name = f"roles-{ROLE_CFG[role].key[:4]}{k}-{os.getpid()}"            # unique per process: the in-tree extension build folder is named after it
        base = 7961 + 3 * k + (30 if role == "data-analyst" else 0)          # the extension build's benefits ports (unused here): just distinct from the defaults
        dist = build_extension(name, {"a": base, "b": base + 1, "c": base + 2})
        built.append(dist)
        w = RoleWorld(role, name, ports[k], dist)
        w.start()
        worlds.append(w)
    return worlds, built


def close_worlds(worlds, built) -> None:
    from evals.study_sim.infra import drop_snapshot, remove_extension_builds

    for w in worlds:
        w.stop()
    remove_extension_builds(built)
    for q in (HERE.parent.parent / "extension").glob("dist-roles-*"):
        import shutil
        shutil.rmtree(q, ignore_errors=True)
    drop_snapshot()


async def _run_many(role: str, specs: list[ParticipantSpec], make_policy_factory, outdir: Path, model_id: str, budget: Budget | None, *, worlds, pace: float, cap: int | None,
                    poll_s: float, skip_done: set[str], tier: str = "", unassisted_only: bool = False, log=print) -> int:
    """Participants are taken in the pre-registered order by whichever worker is free; the spec of each participant does not depend on the worker or on timing."""
    from playwright.async_api import async_playwright

    from evals.study_roles.runner import run_participant

    queue: asyncio.Queue = asyncio.Queue()
    for s in specs:
        if s.pid in skip_done:
            log(f"{s.pid}: already in participants.csv, skipped")
        else:
            queue.put_nowait(s)
    stop = asyncio.Event()
    in_flight = 0
    done = 0
    sim_io.write_provenance(outdir)
    sim_io.write_provenance(outdir / "raw")
    sim_io.write_provenance(outdir / "checks")

    async def worker(pw, world) -> None:
        nonlocal in_flight, done
        while not stop.is_set():
            try:
                spec = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            if budget is not None and not budget.can_start_participant(in_flight):
                log(f"STOP: budget guard (estimated ${budget.usd:.2f} of ${budget.cap_usd:.2f}); not starting {spec.pid}")
                stop.set()
                return
            spec.worker, spec.tier = world.name, tier
            in_flight += 1
            t0 = time.time()
            log(f"{spec.pid} ({spec.arm} {spec.sequence} {spec.persona.code()}) on {world.name}: starting")
            before = budget.per_participant.get(spec.pid, {}).get("usd", 0.0) if budget else 0.0
            try:
                res = await run_participant(spec, world=world, pw=pw, make_policy=make_policy_factory(spec), outdir=outdir, model_id=model_id, pace=pace, cap=cap, poll_s=poll_s,
                                            slots=[x for x in spec.slots() if x.phase != "practice"] if unassisted_only else None, log=log)
            except Exception as exc:  # noqa: BLE001 - BudgetExhausted or a bug in the harness itself
                log(f"{spec.pid}: STOPPED by {type(exc).__name__}: {str(exc)[:200]}")
                stop.set()
                return
            finally:
                in_flight -= 1
            analysis_rows.append_csv(outdir / "participants.csv", res.rows)
            sim_io.append_jsonl(outdir / "actions.jsonl", res.actions)
            (outdir / "checks" / f"{spec.pid}.json").write_text(json.dumps({"participant": spec.pid, "role": role, "arm": spec.arm, "sequence": spec.sequence, "worker": world.name,
                "exclusion": res.exclusion, "wall_s": res.wall_s, "checks": res.checks,
                "cases": [{"phase": c.phase, "block": c.block, "task": c.slot.task, "variant": c.slot.variant, "reason": c.reason, "used": c.used, "capped": c.capped, "wall_s": c.wall_s,
                           "attempt": c.attempt, "outcome": (c.verdict or {}).get("outcome"), "points": (c.verdict or {}).get("points"), "harness_error": c.harness_error,
                           "protocol_violation": c.protocol_violation} for c in res.cases]}, indent=1))
            if budget:
                budget.finished.add(spec.pid)
            spent = (budget.per_participant.get(spec.pid, {}).get("usd", 0.0) - before) if budget else 0.0
            viol = res.checks.get("study_mode_violations") or res.checks.get("study_mode_enforcement_from_store")
            log(f"{spec.pid}: done in {time.time() - t0:.0f}s on {world.name}, exclusion={res.exclusion or 'none'}, outcomes="
                f"{[(c.block, c.phase, (c.verdict or {}).get('outcome')) for c in res.cases]}, cost this participant ${spent:.3f}"
                + (f", total ${budget.usd:.3f}" if budget else "") + (f"  *** STUDY MODE VIOLATION: {viol}" if viol else ""))
            done += 1

    async with async_playwright() as pw:
        await asyncio.gather(*[worker(pw, w) for w in worlds])
    return done


def _parse_plan(plan: str, default: str) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for item in (plan.split(",") if plan else []):          # "1=skipper+obeys,5=expert,6=skipper+presses"
        idx, _, rest = item.partition("=")
        style, *flags = rest.split("+")
        out[int(idx)] = {"style": style, "obeys": "obeys" in flags, "dismisses": "dismisses" in flags, "presses_forbidden": "presses" in flags, "variation": 0}
    return out


def scripted_factory(role: str, plan: dict[int, dict], default: dict, layout: str = ""):
    from evals.study_roles.participant import ScriptedParticipant

    sb = cfg(role).sandbox

    def factory(spec):
        o = plan.get(spec.index) or default

        def make(spec_, slot, phase):
            lay = layout or "v1"
            return ScriptedParticipant(spec_, slot, sb.program(slot.task, slot.variant, o["style"], variation=o.get("variation", 0), layout=lay), sb.snippets(slot.task, slot.variant, lay),
                                       obeys=o["obeys"], dismisses=o["dismisses"], presses_forbidden=o["presses_forbidden"] and phase == "post")
        return make
    return factory


def cmd_fake(a) -> int:
    plan = _parse_plan(a.plan, a.style)
    default = {"style": a.style, "obeys": a.obeys, "dismisses": a.dismisses, "presses_forbidden": False, "variation": 0}
    specs_all = build_participants(a.role)
    wanted = set(plan) or {int(x) for x in a.index.split(",")}
    specs = [s for s in specs_all if s.index in wanted]
    out = FAKE_DIR / (a.name or time.strftime("%Y%m%d-%H%M%S"))
    sim_io.write_provenance(out)
    worlds, built = make_worlds(a.role, a.workers, out)
    try:
        n = asyncio.run(_run_many(a.role, specs, scripted_factory(a.role, plan, default, a.layout), out, "fake", None, worlds=worlds, pace=a.pace, cap=a.cap, poll_s=a.poll, skip_done=set(), tier="fake"))
    finally:
        close_worlds(worlds, built)
    sim_io.write_provenance_tree(out)
    print(f"fake run: {n} participant(s) -> {out}")
    return 0


# ------------------------------------------------------------------------------------------------ model-driven commands (need GO)
def _refuse_without_go() -> int | None:
    if not GO_FILE.exists():
        print("REFUSED: no GO. PLAN.md must be committed by the lead and GO (with a budget) received before any model-driven participant runs.")
        return 2
    if os.environ.get("UNDERSTUDY_MOCK", "").strip().lower() in ("1", "true", "yes", "on"):
        print("REFUSED: UNDERSTUDY_MOCK is set; the model port would return scripted answers, not a model.")
        return 2
    return None


def _port_for(tier: str):
    """The model port for a declared tier. ``fast-low`` sets the fast role's reasoning effort to low BEFORE the port is built (it is read from the environment per call)."""
    if tier == "fast-low":
        os.environ["OPENAI_EFFORT_FAST"] = "low"
    elif tier == "fast":
        os.environ.pop("OPENAI_EFFORT_FAST", None)
    from understudy_agent.models import get_model_port

    port = get_model_port()
    models = getattr(port, "models", None)
    model_id = getattr(models, "fast", "unknown")
    return port, model_id


def _read_json(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def _finish_cost(budget: RolesBudget, outdir: Path, role: str, tier: str, model_id: str) -> None:
    c = budget.summary()
    c.update({"role": role, "tier": tier, "model": model_id})
    (outdir / "cost.json").write_text(json.dumps(c, indent=1))


def cmd_pilot(a) -> int:
    """Feasibility pilot: 3 A/A participants, only their UNASSISTED cases (the pre-test and post-test of each block), discarded from all analysis. Pilots together are capped at US$2."""
    refused = _refuse_without_go()
    if refused:
        return refused
    from evals.study_roles.analysis import pilot_verdict, plan_units
    from evals.study_roles.budget_roles import PILOT_CAP_USD, RolesBudget, apply_tier_prices, carried_usd, pilot_spent_usd
    from evals.study_roles.participant import ModelParticipant

    carried = carried_usd(RESULTS)
    pilot_left = PILOT_CAP_USD - pilot_spent_usd(RESULTS)
    if pilot_left <= 0.05:
        print(f"REFUSED: the pilots have used their US${PILOT_CAP_USD:.2f}. STOP and report; do not escalate without a new plan.")
        return 2
    pin, pout, src = apply_tier_prices(a.tier)
    port, model_id = _port_for(a.tier)
    outdir = RESULTS / a.role / f"pilot_{a.tier}"
    budget = RolesBudget(ledger_path=RESULTS / "cost_ledger.jsonl", carried=carried, cap_usd=min(BUDGET_CAP_USD, carried + pilot_left))      # the hard stop of the pilots
    specs = build_pilot(a.role)

    def factory(spec):
        return lambda spec_, slot, phase: ModelParticipant(port, spec_, budget, a.tier, model_id)

    worlds, built = make_worlds(a.role, a.workers, outdir)
    try:
        n = asyncio.run(_run_many(a.role, specs, factory, outdir, model_id, budget, worlds=worlds, pace=a.pace, cap=a.cap, poll_s=a.poll, skip_done=set(), tier=a.tier, unassisted_only=True))
    finally:
        close_worlds(worlds, built)
        _finish_cost(budget, outdir, a.role, a.tier, model_id)
    rows = analysis_rows.load_rows(outdir / "participants.csv") if (outdir / "participants.csv").exists() else []
    excluded_ids = {r["participant"] for r in rows if str(r.get("exclusion", "")).strip()}
    costs = [v["usd"] for k, v in budget.per_participant.items() if k in budget.finished and k not in excluded_ids]        # the cost of a participant that completed all its cases
    verdict = pilot_verdict(rows, costs)
    if n < len(specs):
        verdict["usable"] = False
        verdict["reasons"].append(f"the pilot is incomplete: {n} of {len(specs)} participants ran (the US$2 pilot cap or a stop)")
    roles_left = 2 if a.role == (list(ROLE_CFG)[0]) else 1
    verdict.update({"role": a.role, "tier": a.tier, "model": model_id, "prices_usd_per_mtok": [pin, pout, src], "participants_run": n,
                    "plan": plan_units(verdict["mean_cost_per_participant_usd"], BUDGET_CAP_USD - budget.usd, roles_left)})
    sim_io.write_provenance(RESULTS / a.role)
    (RESULTS / a.role / f"PILOT_{a.tier}.json").write_text(json.dumps(verdict, indent=1))
    sim_io.write_provenance_tree(RESULTS / a.role)
    print(json.dumps({k: verdict[k] for k in ("usable", "reasons", "share_zero", "share_full", "share_cap_bound", "mean_cost_per_participant_usd", "plan")}, indent=1))
    print(f"pilot {a.role}/{a.tier}: {n} participant(s); total spend estimate ${budget.usd:.3f} of ${BUDGET_CAP_USD:.2f}; pilots so far ${pilot_spent_usd(RESULTS) + budget.usd_this_run:.2f} of ${PILOT_CAP_USD:.2f}")
    if not verdict["usable"]:
        print("THIS OPTION IS NOT USABLE. If every fast option fails, STOP and report: the participant model cannot do these tasks in these sandboxes. Do not escalate to a bigger model without a new plan.")
    return 0


def cmd_run(a) -> int:
    refused = _refuse_without_go()
    if refused:
        return refused
    from evals.study_roles.analysis import plan_units
    from evals.study_roles.budget_roles import RolesBudget, apply_tier_prices, carried_usd
    from evals.study_roles.participant import ModelParticipant

    pilot = _read_json(RESULTS / a.role / f"PILOT_{a.tier}.json")
    if not pilot or not pilot.get("usable"):
        print(f"REFUSED: no usable pilot for {a.role} on tier {a.tier} (run `pilot` first; the study runs only on a participant option that passed the pre-registered criteria).")
        return 2
    carried = carried_usd(RESULTS)
    plan = plan_units(pilot["mean_cost_per_participant_usd"], BUDGET_CAP_USD - carried, a.roles_left)
    if not plan["run"]:
        print(f"REFUSED: {plan['why']} (measured pilot cost US${pilot['mean_cost_per_participant_usd']}, US${BUDGET_CAP_USD - carried:.2f} left, {a.roles_left} role(s) left).")
        return 2
    units = min(a.units, plan["units"])
    print(f"plan: {units} unit(s) = {8 * units} participants ({4 * units} coached + {4 * units} A/A); estimated cost US${units * plan['unit_cost_usd']:.2f}")
    apply_tier_prices(a.tier)
    port, model_id = _port_for(a.tier)
    outdir = RESULTS / a.role
    budget = RolesBudget(ledger_path=RESULTS / "cost_ledger.jsonl", carried=carried)
    specs = build_participants(a.role)[:8 * units]
    done_ids: set[str] = set()
    csv_path = outdir / "participants.csv"
    if csv_path.exists():
        import csv
        with csv_path.open() as fh:
            done_ids = {r["participant"] for r in csv.DictReader(fh)}

    def factory(spec):
        return lambda spec_, slot, phase: ModelParticipant(port, spec_, budget, a.tier, model_id)

    worlds, built = make_worlds(a.role, a.workers, outdir)
    try:
        n = asyncio.run(_run_many(a.role, specs, factory, outdir, model_id, budget, worlds=worlds, pace=a.pace, cap=a.cap, poll_s=a.poll, skip_done=done_ids, tier=a.tier))
    finally:
        close_worlds(worlds, built)
        (outdir / "run").mkdir(parents=True, exist_ok=True)
        _finish_cost(budget, outdir / "run", a.role, a.tier, model_id)
    from evals.study_roles import report
    report.write_all(a.role, outdir)
    print(f"run {a.role}: {n} participant(s); spend estimate ${budget.usd:.3f} of ${budget.cap_usd:.2f}")
    return 0


def cmd_experts(a) -> int:
    """Record scripted EXPERT runs (no model) through the real pipeline: one case per run, coach off, events and cogs saved under experts/<role>/."""
    from playwright.async_api import async_playwright

    from evals.study_roles import experts as X
    from evals.study_roles.participant import ScriptedParticipant
    from evals.study_roles.runner import run_participant

    sb = cfg(a.role).sandbox
    outdir = HERE / "experts" / a.role
    plan = X.expert_plan(a.role, a.count)
    only = {int(x) for x in a.only.split(",")} if a.only else set(range(1, len(plan) + 1))
    worlds, built = make_worlds(a.role, 1, outdir)
    world = worlds[0]
    saved: list[Path] = []

    async def go() -> None:
        async with async_playwright() as pw:
            for n, (task, variant, variation) in enumerate(plan, start=1):
                if n not in only:
                    continue
                spec = X.expert_spec(a.role, n, task, variant)
                slot = X.expert_slot(a.role, task, variant)
                box: dict = {}

                def make(spec_, slot_, phase, task=task, variant=variant, variation=variation):
                    return ScriptedParticipant(spec_, slot_, sb.program(task, variant, "expert", variation=variation), sb.snippets(task, variant))

                def on_finish(engine, box=box, spec=spec):
                    from evals.study_sim.infra import read_events
                    box["events"] = read_events(engine.url, spec.person)

                res = await run_participant(spec, world=world, pw=pw, make_policy=make, outdir=outdir, model_id="scripted-expert", pace=a.pace, slots=[slot], on_finish=on_finish)
                verdict = res.cases[0].verdict if res.cases else None
                saved.append(X.save_run(a.role, outdir, n, task, variant, variation, verdict, box.get("events", [])))
                print(f"expert run {n}: {task} v{variant} variation {variation}: {(verdict or {}).get('outcome')}, {len(box.get('events', []))} events, exclusion={res.exclusion or 'none'}", flush=True)

    try:
        asyncio.run(go())
    finally:
        close_worlds(worlds, built)
    m = X.manifest(outdir, a.role)
    sim_io.write_provenance_tree(outdir)
    print(f"{m['runs']} expert runs for {a.role}, all correct: {m['all_correct']} -> {outdir}")
    return 0


def cmd_analyze(a) -> int:
    from evals.study_roles import report

    report.write_all(a.role, RESULTS / a.role if not a.dir else Path(a.dir))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="study_roles")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fake")
    f.add_argument("--role", choices=list(ROLE_CFG), required=True)
    f.add_argument("--index", default="1")
    f.add_argument("--style", choices=["skipper", "expert", "claimer"], default="skipper")
    f.add_argument("--obeys", action="store_true")
    f.add_argument("--dismisses", action="store_true")
    f.add_argument("--plan", default="", help="per participant: 1=skipper+obeys,5=expert,6=skipper+presses (overrides --index/--style)")
    f.add_argument("--name", default="")
    f.add_argument("--layout", default="", choices=["", "v1", "v2"])
    f.add_argument("--pace", type=float, default=2.0)
    f.add_argument("--cap", type=int, default=None)
    f.add_argument("--poll", type=float, default=3.0)
    f.add_argument("--workers", type=int, default=1)
    f.set_defaults(fn=cmd_fake)
    e = sub.add_parser("experts")
    e.add_argument("--role", choices=list(ROLE_CFG), required=True)
    e.add_argument("--count", type=int, default=8)
    e.add_argument("--pace", type=float, default=1.5)
    e.add_argument("--only", default="", help="re-record only these run numbers, e.g. 3,4")
    e.set_defaults(fn=cmd_experts)
    pl = sub.add_parser("pilot")
    pl.add_argument("--role", choices=list(ROLE_CFG), required=True)
    pl.add_argument("--tier", choices=["fast", "fast-low"], required=True)
    pl.add_argument("--pace", type=float, default=2.0)
    pl.add_argument("--cap", type=int, default=None)
    pl.add_argument("--poll", type=float, default=3.0)
    pl.add_argument("--workers", type=int, default=1)
    pl.set_defaults(fn=cmd_pilot)
    r = sub.add_parser("run")
    r.add_argument("--role", choices=list(ROLE_CFG), required=True)
    r.add_argument("--tier", choices=["fast", "fast-low"], required=True)
    r.add_argument("--units", type=int, default=3)
    r.add_argument("--roles-left", type=int, default=2, help="how many roles still to run, this one included (splits what is left of the budget)")
    r.add_argument("--pace", type=float, default=2.0)
    r.add_argument("--cap", type=int, default=None)
    r.add_argument("--poll", type=float, default=3.0)
    r.add_argument("--workers", type=int, default=2, help="at most 2 (the lead's limit while the machine is shared)")
    r.set_defaults(fn=cmd_run)
    an = sub.add_parser("analyze")
    an.add_argument("--role", choices=list(ROLE_CFG), required=True)
    an.add_argument("--dir", default="")
    an.set_defaults(fn=cmd_analyze)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
