"""Command line for the bake-off.

    uv run --env-file .env python -m evals.modelbench --budget 3                 # build shots if needed, run everything, write the report
    uv run --env-file .env python -m evals.modelbench --smoke 10                 # 10 pointing cases x 3 contenders only
    uv run --env-file .env python -m evals.modelbench --dry-run                  # list the jobs and the estimated cost; no live call
    uv run python -m evals.modelbench --report-only                              # rebuild the report from the cache; no live call
    options: --only pointing,steps,verifier,glance   --contenders gemini_fast,gemini_accurate,openai_fast   --rebuild-shots

Resumable: every finished call is cached; a rerun makes only the missing calls. The budget guard (default US$3 across ALL live calls of
this track, counted at 1.25x the estimate) stops the run and records the dropped cells. Live calls happen only here, never in pytest.
Sandbox screenshots only: nothing here captures or sends the real screen. Nothing prints a key.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))

from evals.modelbench import analyze, cases as cm, report  # noqa: E402
from evals.modelbench.budget import Budget  # noqa: E402
from evals.modelbench.cache import ResultCache  # noqa: E402
from evals.modelbench.contenders import NAMES, Contender, check_environment  # noqa: E402
from evals.modelbench.runner import Job, Runner, key_for  # noqa: E402

CACHE = HERE / "cache"
GROUPS = ("pointing", "steps", "verifier", "glance", "latency")
LATENCY_REPS = 15
GLANCE_REPS = 5


def select_cases(manifest: dict) -> list[dict]:
    """The pointing cases that get model calls: every base case, a seeded sample of v2 and dark, and the injected cases whose
    injection is visible in the screenshot."""
    shots = cm.shot_index(manifest)
    cases = cm.cases_from(manifest)
    # an input (screenshot pixels + description) is asked once: a v2 or dark case that is pixel-identical to a base case is the same
    # input, so it is not a new case. Only cases with a new input can fill the secondary samples.
    base_inputs = {(shots[c.shot_id]["sha"], c.desc) for c in cases if c.cond == "base"}
    allc = [c for c in cases if not (c.cond == "injected" and not shots[c.shot_id]["injection_visible"])
            and not (c.cond != "base" and (shots[c.shot_id]["sha"], c.desc) in base_inputs)]
    sample = cm.sample_cases(allc)
    out = []
    for cond in ("base", "v2", "injected", "dark"):
        out += [c.__dict__ for c in sample[cond]]
    return out


def build_jobs(manifest: dict, only: set[str], smoke: int | None) -> list[Job]:
    shots = cm.shot_index(manifest)
    jobs: list[Job] = []
    sel = manifest["selected_cases"]
    if smoke:
        pos = [c for c in sel if c["cond"] == "base" and c["kind"] == "positive"]
        neg = [c for c in sel if c["cond"] == "base" and c["kind"] == "negative"]
        step = max(1, len(pos) // max(1, smoke - 3))
        sel = pos[::step][: smoke - 3] + neg[:: max(1, len(neg) // 3)][:3]
        only = {"pointing"}
    if "pointing" in only:
        for c in sel:
            s = shots[c["shot_id"]]
            jobs.append(Job("point_desc", c["case_id"], s["file"], s["sha"], desc=c["desc"], group=c["cond"]))
    if "verifier" in only:
        for it in manifest["verifier"]:
            jobs.append(Job("verify", it["id"], it["file"], it["sha"], check="page_shows_result", group=it["group"]))
    if "glance" in only:
        for screen in analyze.GLANCE_SCREENS:
            s = shots[f"base__{screen}"]
            for rep in range(GLANCE_REPS):
                jobs.append(Job("glance", screen, s["file"], s["sha"], rep=rep, group="base"))
    if "latency" in only and not smoke:
        first = next(c for c in manifest["selected_cases"] if c["cond"] == "base" and c["kind"] == "positive")
        s = shots[first["shot_id"]]
        for rep in range(LATENCY_REPS):
            jobs.append(Job("point_desc", first["case_id"], s["file"], s["sha"], desc=first["desc"], rep=100 + rep, group="latency"))
    if "steps" in only:
        for c in manifest["step_cases"]:
            s = shots[c["shot_id"]]
            jobs.append(Job("point_step", c["case_id"], s["file"], s["sha"], step=c["step"], group=c["cond"]))
    return jobs


def collect_rows(cache: ResultCache, contenders: list[Contender], jobs: list[Job]) -> tuple[list[dict], int]:
    """Cached rows for exactly these jobs, found by cache key (so a re-render that renumbers the cases cannot misalign anything), each
    labelled with its job's case id. A job whose input (key) already appeared is skipped: identical inputs are counted once.
    Returns (rows, duplicate inputs skipped)."""
    out: list[dict] = []
    dup = 0
    for c in contenders:
        seen: set[str] = set()
        for j in jobs:
            k = key_for(c, j)
            if k in seen:
                dup += 1
                continue
            seen.add(k)
            row = cache.peek(k)
            if row is not None:
                out.append({**row, "kind": j.kind, "contender": c.name, "case_id": j.case_id, "rep": j.rep})
    return out, dup


def assemble(manifest: dict, rows: list[dict], contenders: list[str]) -> dict:
    sections = {
        "pointing": analyze.pointing_section(manifest, rows, contenders, kind="point_desc", id_key="selected_cases"),
        "pointing_step_ids": analyze.pointing_section(manifest, rows, contenders, kind="point_step", id_key="step_cases"),
        "verifier": analyze.verifier_section(manifest, rows, contenders),
        "glance": analyze.glance_section(manifest, rows, contenders),
    }
    sections["latency_recheck"] = analyze.latency_section(rows, contenders, sections["pointing"]["cells"])
    # routed cells only make sense for pointing; the step-id section keeps its simulated cells too (same rule, smaller n)
    sections["recommendation"] = report.recommend(sections)
    return sections


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m evals.modelbench", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--budget", type=float, default=3.0, help="US$ cap across ALL live calls of this track (default 3)")
    ap.add_argument("--smoke", type=int, default=0, help="run only N pointing cases (all contenders)")
    ap.add_argument("--only", default=",".join(GROUPS), help="comma list of: " + ", ".join(GROUPS))
    ap.add_argument("--contenders", default=",".join(NAMES))
    ap.add_argument("--rebuild-shots", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--cache-dir", default=str(CACHE))
    ap.add_argument("--out-json", default=str(ROOT / "data" / "eval" / "modelbench.json"))
    ap.add_argument("--out-md", default=str(HERE / "REPORT.md"))
    ap.add_argument("--out-yaml", default=str(HERE / "routing.recommended.yaml"))
    a = ap.parse_args(argv)

    cache_dir = Path(a.cache_dir)
    only = {x.strip() for x in a.only.split(",") if x.strip()}
    contenders = [Contender(n) for n in a.contenders.split(",") if n.strip()]
    bad = only - set(GROUPS)
    if bad:
        ap.error(f"unknown group(s): {', '.join(sorted(bad))}")

    # the bench is live by definition; its egress ledger lives in the cache dir, never in the real data dir
    os.environ["UNDERSTUDY_MOCK"] = "0"
    os.environ["UNDERSTUDY_DATA_DIR"] = str(cache_dir / "data")

    shots_dir = cache_dir / "shots"
    if a.rebuild_shots or not (shots_dir / "manifest.json").exists():
        print("rendering sandbox screenshots (headless, ephemeral ports) ...", flush=True)
        manifest = cm.build(shots_dir)
        print(f"  {len(manifest['shots'])} shots, {len(manifest['cases'])} cases, {len(manifest['verifier'])} verifier images", flush=True)
    else:
        manifest = cm.load_manifest(shots_dir)
    manifest["selected_cases"] = select_cases(manifest)

    cache = ResultCache(cache_dir / "results.jsonl")
    budget = Budget(a.budget, cache_dir / "spend.jsonl")
    models = {c.name: c.model for c in contenders}
    jobs = build_jobs(manifest, only, a.smoke or None)

    if a.dry_run:
        from collections import Counter

        n = Counter(j.kind for j in jobs)
        est = sum(c.est_cost() * len(jobs) for c in contenders)
        print(f"jobs per contender: {dict(n)}; contenders: {[c.name for c in contenders]}; "
              f"cached results: {len(cache)}; worst-case estimate US${est:.2f} (guard cap US${a.budget}, spent so far US${budget.spent:.3f})")
        return 0

    counts = {"cached": 0, "live": 0, "failed": 0, "dropped": 0}
    if not a.report_only:
        check_environment()
        from understudy_agent.models.boot import _openai_boot_check, gemini_boot_check

        for name, fn in (("openai", lambda: _openai_boot_check(raise_on_fail=False, out=print)),
                         ("gemini", lambda: gemini_boot_check(raise_on_fail=False, out=print))):
            rep = fn()
            if not rep.ok:
                print(f"boot check failed for {name}; not running", flush=True)
                return 2
        print(f"models: {models}; est. spend so far US${budget.spent:.3f} of US${a.budget}", flush=True)
        runner = Runner(shots_dir, cache, budget)
        print(f"running {len(jobs)} jobs x {len(contenders)} contenders ...", flush=True)
        runner.run(contenders, jobs)
        counts = runner.counts
        print(f"calls: {counts}; est. spend US${budget.spent:.3f}; dropped {len(budget.dropped)}", flush=True)

    rows, dup = collect_rows(cache, contenders, jobs)
    sections = assemble(manifest, rows, [c.name for c in contenders])
    sections["recommendation"]["duplicate_inputs_skipped"] = dup
    spend_lines = sum(1 for _ in (cache_dir / "spend.jsonl").open()) if (cache_dir / "spend.jsonl").exists() else 0
    counts = {**counts, "live_calls_all_runs": spend_lines, "cache_rows": len(cache)}
    j = report.build_json(sections, models=models, budget=budget.summary(), counts=counts,
                          apis={c.name: c.api for c in contenders}, thinking={c.name: c.thinking for c in contenders})
    report.write_all(j, out_json=Path(a.out_json), out_md=Path(a.out_md), out_yaml=Path(a.out_yaml))
    print(f"wrote {a.out_json}, {a.out_md}, {a.out_yaml}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
