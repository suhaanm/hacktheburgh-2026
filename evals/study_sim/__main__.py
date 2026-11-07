"""Command line.

    uv run --package understudy-agent python -m evals.study_sim fake --index 1 --style skipper --obeys      # harness test, NO model
    uv run --package understudy-agent --env-file .env python -m evals.study_sim run [--only 1,2] [--dry-budget]   # model participants (needs GO)
    uv run --package understudy-agent python -m evals.study_sim analyze                                        # summary.json + REPORT.md

``fake`` writes to evals/study_sim/fake_runs/ and never to results/. ``run`` refuses to start unless the file evals/study_sim/GO exists
(it is created only after the lead has committed PLAN.md and replied GO).
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

from evals.study_sim import analysis_io  # noqa: E402
from evals.study_sim.budget import Budget  # noqa: E402
from evals.study_sim.design import build_participants, load_cases  # noqa: E402

GO_FILE = HERE / "GO"
RESULTS = HERE / "results"
FAKE_DIR = HERE / "fake_runs"


def _lock():
    from understudy_agent.sandbox_sites.lock import acquire, release
    return acquire, release


async def _run_many(specs, make_policy_factory, outdir: Path, model_id: str, budget: Budget | None, *, worlds, pace: float, cap: int, poll_s: float,
                    skip_done: set[str], log=print) -> int:
    """Participants are taken in the pre-registered run order by whichever worker (private world) is free; the spec of each participant
    (sequence, arm, cases, persona) is fixed in advance and does not depend on the worker or on timing."""
    from playwright.async_api import async_playwright
    from evals.study_sim.runner import run_participant

    analysis_io.write_provenance(outdir)                          # refuses anything under evals/study/ or through a symlink
    analysis_io.write_provenance(outdir / "raw")
    analysis_io.write_provenance(outdir / "checks")

    queue: asyncio.Queue = asyncio.Queue()
    for s in specs:
        if s.pid in skip_done:
            log(f"{s.pid}: already in participants.csv, skipped")
        else:
            queue.put_nowait(s)
    stop = asyncio.Event()
    in_flight = 0
    done = 0

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
            spec.worker = world.name
            in_flight += 1
            t0 = time.time()
            log(f"{spec.pid} ({spec.arm} {spec.sequence} {spec.variant} {spec.persona.code()}) on {world.name}: starting")
            before = budget.per_participant.get(spec.pid, {}).get("usd", 0.0) if budget else 0.0
            try:
                res = await run_participant(spec, world=world, pw=pw, make_policy=make_policy_factory(spec), outdir=outdir, model_id=model_id,
                                            lock=_lock() if world.shared else (None, None), pace=pace, cap=cap, poll_s=poll_s, log=log)
            except Exception as exc:  # noqa: BLE001 - BudgetExhausted or a bug in the harness itself
                log(f"{spec.pid}: STOPPED by {type(exc).__name__}: {str(exc)[:200]}")
                stop.set()
                return
            finally:
                in_flight -= 1
            analysis_io.append_csv(outdir / "participants.csv", res.rows)
            analysis_io.append_jsonl(outdir / "actions.jsonl", res.actions)
            (outdir / "checks").mkdir(parents=True, exist_ok=True)
            (outdir / "checks" / f"{spec.pid}.json").write_text(json.dumps({"participant": spec.pid, "arm": spec.arm, "sequence": spec.sequence,
                "worker": world.name, "exclusion": res.exclusion, "wall_s": res.wall_s, "checks": res.checks,
                "cases": [{"phase": c.phase, "block": c.block, "reason": c.reason, "used": c.used, "capped": c.capped, "wall_s": c.wall_s, "attempt": c.attempt,
                           "score": c.score, "harness_error": c.harness_error, "protocol_violation": c.protocol_violation} for c in res.cases]}, indent=1))
            if budget:
                budget.finished.add(spec.pid)
            spent = (budget.per_participant.get(spec.pid, {}).get("usd", 0.0) - before) if budget else 0.0
            viol = res.checks.get("study_mode_violations") or res.checks.get("study_mode_enforcement_from_store")
            log(f"{spec.pid}: done in {time.time() - t0:.0f}s on {world.name}, exclusion={res.exclusion or 'none'}, scores="
                f"{[(c.block, c.phase, c.score) for c in res.cases if c.score]}, cost this participant ${spent:.3f}"
                + (f", total ${budget.usd:.3f}" if budget else "") + (f"  *** STUDY MODE VIOLATION: {viol}" if viol else ""))
            done += 1

    async with async_playwright() as pw:
        await asyncio.gather(*[worker(pw, w) for w in worlds])
    return done


def make_worlds(n: int, shared: bool, outdir: Path | None = None, freeze_from: Path | None = None):
    """``freeze_from``: reuse an earlier run's frozen code snapshot and extension builds (``frozen_run4/``) instead of taking new ones, so a later run
    meets exactly the same coach, sites and extension (run 5)."""
    from evals.study_sim.infra import SNAPSHOT, World, build_extension, shared_world, snapshot_pipeline

    if freeze_from is not None:
        info = json.loads((Path(freeze_from) / "snapshot" / "SNAPSHOT.json").read_text())
        info = {**info, "path": str(Path(freeze_from) / "snapshot"), "frozen_from": str(freeze_from)}
        SNAPSHOT.update(info)
        SNAPSHOT["frozen"] = True
    else:
        info = snapshot_pipeline()
    if outdir is not None:
        analysis_io.write_provenance(outdir)
        (outdir / "snapshot.json").write_text(json.dumps({k: v for k, v in info.items() if k != "path"}, indent=1))
    print(f"pipeline snapshot {info['fingerprint']} of git {info['git_head'][:8]} (+{info['uncommitted_files_in_snapshot_dirs']} uncommitted files)", flush=True)

    if shared:
        w = shared_world()
        if not w.up():
            raise SystemExit("the shared sandbox sites on 7801-7803 are not running (uv run python -m understudy_agent.sandbox_sites)")
        return [w], []
    worlds, built = [], []
    for k in range(n):
        name = f"ssim{k}"
        base = 7911 + 10 * k
        ports = {"a": base, "b": base + 1, "c": base + 2}
        if freeze_from is not None:
            dist = Path(freeze_from) / f"ext-{name}"
        else:
            dist = build_extension(name, ports)
            built.append(dist)
        w = World(name, ports, dist)
        w.start_sites()
        worlds.append(w)
    return worlds, built


def close_worlds(worlds, built) -> None:
    from evals.study_sim.infra import drop_snapshot, remove_extension_builds

    for w in worlds:
        w.stop()
    remove_extension_builds(built)
    drop_snapshot()


def cmd_fake(a) -> int:
    from evals.study_sim.participant import FakeParticipant

    plan: dict[int, dict] = {}
    for item in (a.plan.split(",") if a.plan else []):          # "3=skipper+dismisses,5=thorough,6=skipper+submits"
        idx, _, rest = item.partition("=")
        style, *flags = rest.split("+")
        plan[int(idx)] = {"style": style, "obeys": "obeys" in flags, "dismisses": "dismisses" in flags, "submits": "submits" in flags}
    wanted = set(plan) or {int(x) for x in a.index.split(",")}
    specs = [s for s in build_participants() if s.index in wanted]
    out = FAKE_DIR / (a.name or time.strftime("%Y%m%d-%H%M%S"))
    out.mkdir(parents=True, exist_ok=True)

    def factory(spec):
        def make(spec_, case, phase, world):
            urls = {"gov": world.url_gov, "quick": world.url_quick, "note": world.url_note}
            o = plan.get(spec_.index) or {"style": a.style, "obeys": a.obeys, "dismisses": a.dismisses, "submits": a.submits}
            return FakeParticipant(spec_, case["site_inputs"], case["household"]["case_ref"], urls=urls, style=o["style"], obeys=o["obeys"],
                                   dismisses=o["dismisses"], submits=o["submits"] and phase == "post")
        return make

    worlds, names = make_worlds(a.workers, a.shared, out)
    try:
        n = asyncio.run(_run_many(specs, factory, out, "fake", None, worlds=worlds, pace=a.pace, cap=a.cap, poll_s=a.poll, skip_done=set()))
    finally:
        close_worlds(worlds, names)
    print(f"fake run: {n} participant(s) -> {out}")
    return 0


def cmd_run(a) -> int:
    if not GO_FILE.exists():
        print("REFUSED: no GO. The plan must be committed by the lead and GO received before any model-driven participant runs.")
        return 2
    if os.environ.get("UNDERSTUDY_MOCK", "").strip().lower() in ("1", "true", "yes", "on"):
        print("REFUSED: UNDERSTUDY_MOCK is set; the model port would return scripted answers, not a model.")
        return 2
    from understudy_agent.models import get_model_port
    from evals.study_sim.participant import ModelParticipant

    port = get_model_port()
    model_id = getattr(getattr(port, "models", None), "fast", "unknown")
    budget = Budget(ledger_path=RESULTS / "cost_ledger.jsonl")
    for ab in sorted(HERE.glob("aborted_run*/cost.json")):
        budget.carry(ab)
    specs = build_participants()
    if a.only:
        keep = {int(x) for x in a.only.split(",")}
        specs = [s for s in specs if s.index in keep]
    done_ids: set[str] = set()
    csv_path = RESULTS / "participants.csv"
    if csv_path.exists():
        import csv
        with csv_path.open() as fh:
            done_ids = {r["participant"] for r in csv.DictReader(fh)}

    def factory(spec):
        return lambda spec_, case, phase, world: ModelParticipant(port, spec_, budget, model_id)

    worlds, names = make_worlds(a.workers, a.shared, RESULTS)
    try:
        n = asyncio.run(_run_many(specs, factory, RESULTS, model_id, budget, worlds=worlds, pace=a.pace, cap=a.cap, poll_s=a.poll, skip_done=done_ids))
    finally:
        close_worlds(worlds, names)
        (RESULTS / "cost.json").write_text(json.dumps(budget.summary(), indent=1))
    print(f"run: {n} participant(s); spend estimate ${budget.usd:.3f}")
    return 0


RESULTS5 = HERE / "results_run5"
GO5_FILE = HERE / "GO5"
FROZEN4 = HERE / "frozen_run4"
# declared in PLAN_RUN5.md: the frozen pipeline of run 4 that run 5 must meet, unchanged
RUN5_PIPELINE_FINGERPRINT = "5630b3c99e9f734a"
RUN5_EXT_FINGERPRINTS = {"ext-ssim0": "456cdba315422688", "ext-ssim1": "8aca835fb01cd573", "ext-ssim2": "c32fc1e85d21f4df"}
RUN5_LABEL = "run 5, EXPLORATORY: the same fast-tier model with reasoning effort raised to low (option P2), same sites and coach as run 4"


def _run5_limitations() -> list:
    return [{"id": "run5-exploratory", "severity": "high",
             "text": "Run 5 is exploratory. It was designed after run 4 hit the floor, uses the same model with its reasoning effort raised to low (option P2, chosen from the options declared in PLAN_RUN5.md before any call; the planner option was withdrawn as unaffordable), and has far fewer participants than run 4. Its pilot of three participants was only used to decide whether to proceed and is in no analysis."},
            {"id": "run5-power", "severity": "high",
             "text": "With 8 coached participants the interval excludes zero with probability about 6% under no effect, 10%, 16% and 49% for a small, medium and large true effect (engine-analytics Monte Carlo); sign-flip p below 0.05 is 1%, 2%, 6% and 22%. A null says almost nothing."}]


def cmd_run5(a) -> int:
    from understudy_agent.models import get_model_port
    from evals.study_sim import pilot as pilot_mod
    from evals.study_sim.design import build_pilot_participants, build_run5_participants
    from evals.study_sim.participant import ModelParticipant

    if not GO5_FILE.exists():
        print("REFUSED: no GO5. PLAN_RUN5.md must be committed by the lead and GO received before any model call of run 5.")
        return 2
    if os.environ.get("UNDERSTUDY_MOCK", "").strip().lower() in ("1", "true", "yes", "on"):
        print("REFUSED: UNDERSTUDY_MOCK is set.")
        return 2
    if not (os.environ.get("STUDY_SIM_PRICE_IN") and os.environ.get("STUDY_SIM_PRICE_OUT")):
        print("REFUSED: run 5 needs STUDY_SIM_PRICE_IN and STUDY_SIM_PRICE_OUT (US$ per million tokens, the assumed 0.75 and 4.50 of the fast tier) so the US$6 guard is real.")
        return 2
    from evals.study_sim.infra import fingerprint_dir

    if fingerprint_dir(FROZEN4 / "snapshot") != RUN5_PIPELINE_FINGERPRINT or any(
            fingerprint_dir(FROZEN4 / k, ()) != v for k, v in RUN5_EXT_FINGERPRINTS.items() if k in {f"ext-ssim{i}" for i in range(a.workers)}):
        print("REFUSED: frozen_run4/ no longer matches the pipeline and extension fingerprints declared in PLAN_RUN5.md: run 5 must meet exactly run 4's coach, sites and extension.")
        return 2
    stage = a.stage
    out = RESULTS5 / stage
    analysis_io.write_provenance(RESULTS5)
    analysis_io.write_provenance(out)
    specs = build_pilot_participants() if stage == "pilot" else build_run5_participants()
    if stage == "main":
        dec_file = RESULTS5 / "pilot" / "PILOT_DECISION.json"
        if not dec_file.exists() or not json.loads(dec_file.read_text()).get("pass"):
            print("REFUSED: the pilot has not passed its declared criterion (run `pilot-decide` first); run 5 proper does not start.")
            return 2
        specs = specs[:int(json.loads(dec_file.read_text())["n_planned"])]
    os.environ["OPENAI_EFFORT_FAST"] = "low"                      # option P2 of PLAN_RUN5.md (amendment 1): the fast tier at reasoning effort low
    port = get_model_port()
    model_id = f"{getattr(getattr(port, 'models', None), 'fast', 'unknown')}@effort-low"
    budget = pilot_mod_budget(RESULTS5 / "cost_ledger.jsonl")
    if stage == "main":
        budget.carry(RESULTS5 / "pilot" / "cost.json")
    csv_path = out / "participants.csv"
    done_ids: set[str] = set()
    if csv_path.exists():
        import csv
        with csv_path.open() as fh:
            done_ids = {r["participant"] for r in csv.DictReader(fh)}

    def factory(spec):
        return lambda spec_, case, phase, world: ModelParticipant(port, spec_, budget, model_id, tier="fast")

    worlds, built = make_worlds(a.workers, False, out, freeze_from=FROZEN4)
    try:
        n = asyncio.run(_run_many(specs, factory, out, model_id, budget, worlds=worlds, pace=a.pace, cap=a.cap, poll_s=a.poll, skip_done=done_ids))
    finally:
        close_worlds(worlds, built)
        (out / "cost.json").write_text(json.dumps(budget.summary(), indent=1))
    print(f"run5 {stage}: {n} participant(s); spend estimate ${budget.usd:.3f} of the US${budget.cap_usd:.0f} cap (pilot included; run 4 and the aborted runs are not part of it)")
    return 0


def pilot_mod_budget(ledger: Path) -> Budget:
    from evals.study_sim import pilot as pilot_mod

    return Budget(cap_usd=pilot_mod.BUDGET_USD, ledger_path=ledger)


def cmd_pilot_decide(a) -> int:
    from evals.study_sim import pilot as pilot_mod

    d = pilot_mod.decide_from_dir(RESULTS5 / "pilot")
    print(json.dumps(d, indent=1))
    return 0 if d["pass"] else 3


def cmd_analyze5(a) -> int:
    from evals.study_sim import report
    from evals.study_sim.design import build_run5_participants

    dec = RESULTS5 / "pilot" / "PILOT_DECISION.json"
    n_planned = json.loads(dec.read_text()).get("n_planned", 12) if dec.exists() else 12
    expected = (8, 4) if n_planned >= 12 else (8, 0)
    report.write_all(RESULTS5 / "main", expected=expected, specs=build_run5_participants(), run_label=RUN5_LABEL, extra_limitations=_run5_limitations(),
                     report_path=RESULTS5 / "REPORT_RUN5.md")
    analysis_io.write_provenance_tree(RESULTS5)
    return 0


def cmd_analyze(a) -> int:
    from evals.study_sim import report
    report.write_all(RESULTS if not a.dir else Path(a.dir))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="study_sim")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fake")
    f.add_argument("--index", default="1")
    f.add_argument("--style", choices=["skipper", "thorough"], default="skipper")
    f.add_argument("--obeys", action="store_true")
    f.add_argument("--dismisses", action="store_true")
    f.add_argument("--submits", action="store_true")
    f.add_argument("--plan", default="", help="per participant: 3=skipper+dismisses,5=thorough,6=skipper+submits (overrides --index/--style)")
    f.add_argument("--name", default="")
    f.add_argument("--pace", type=float, default=2.0)
    f.add_argument("--cap", type=int, default=60)
    f.add_argument("--poll", type=float, default=3.0)
    f.add_argument("--workers", type=int, default=1)
    f.add_argument("--shared", action="store_true", help="fallback: the shared sites on 7801-7803 under sandbox_lock instead of private worlds")
    f.set_defaults(fn=cmd_fake)
    r = sub.add_parser("run")
    r.add_argument("--only", default="")
    r.add_argument("--pace", type=float, default=2.0)
    r.add_argument("--cap", type=int, default=60)
    r.add_argument("--poll", type=float, default=3.0)
    r.add_argument("--workers", type=int, default=3)
    r.add_argument("--shared", action="store_true")
    r.set_defaults(fn=cmd_run)
    r5 = sub.add_parser("run5")
    r5.add_argument("--stage", choices=["pilot", "main"], required=True)
    r5.add_argument("--pace", type=float, default=2.0)
    r5.add_argument("--cap", type=int, default=60)
    r5.add_argument("--poll", type=float, default=3.0)
    r5.add_argument("--workers", type=int, default=3)
    r5.set_defaults(fn=cmd_run5)
    pd = sub.add_parser("pilot-decide")
    pd.set_defaults(fn=cmd_pilot_decide)
    a5 = sub.add_parser("analyze5")
    a5.set_defaults(fn=cmd_analyze5)
    an = sub.add_parser("analyze")
    an.add_argument("--dir", default="")
    an.set_defaults(fn=cmd_analyze)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
