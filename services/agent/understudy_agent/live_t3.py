"""LIVE tier-3 evaluation on the sandbox sites (REQ-7 AGT, evals/agentic/PLAN.md). Needs a key; run by hand.

Always: the BrowserPage actuator on the headless sandbox (no desktop event, no real screen), the real gate in the path,
fact handles, synthetic households. A persistent spend ledger (evals/agentic/results/spend_ledger.json) holds a HARD cap on
NEW live spend: before every model call the cumulative estimate is checked, and a run the guard cuts short is discarded.

    # the diagnostic smoke: ONE calculator, tier 3 only, prints the model's own closing words (digit runs masked)
    uv run python -m understudy_agent.live_t3 smoke --site b --household 1 --budget 1.0

    # a development round: whole households (three calculators and the case note), tier 3 only
    uv run python -m understudy_agent.live_t3 round --households 10 --seed 7001 --condition clean --label iter1
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

from .audit import AuditLog
from .live_eval import BudgetExceeded, LiveModel, code_check, prices, switch_for
from .models import get_model_port
from .navigator import CalculatorJob, Navigator
from .orchestrator import BenefitsRun, RunOptions
from .queue import ApprovalQueue
from .sandbox_sites.households import generate_households
from .sandbox_sites.runner import SandboxCluster
from .security.dataflow import host_key
from .security.denylist import Denylist
from .supervisor import data_dir
from .tiers.browser import BrowserHost
from .tiers.safety import Guard

CAP_USD = float(os.environ.get("AGENT_LIVE_CAP_USD", "20"))          # NEW live spend, placeholder rates (5 and 30 USD per M tokens)
LOWER = (0.75, 4.50)                                                  # the lower, mini-class rates, reported next to it
RESULTS = Path(__file__).resolve().parents[3] / "evals" / "agentic" / "results"
LEDGER = RESULTS / "spend_ledger.json"


def ledger() -> dict[str, Any]:
    try:
        return json.loads(LEDGER.read_text())
    except (OSError, ValueError):
        return {"cap_usd": CAP_USD, "entries": []}


def spent() -> float:
    return round(sum(e["cost_placeholder_usd"] for e in ledger()["entries"]), 4)


def model_ids() -> dict[str, str]:
    try:
        from .models.config import ModelIds

        return ModelIds.from_env().as_dict()
    except Exception:  # noqa: BLE001
        return {}


def record(label: str, kind: str, tin: int, tout: int, cost_placeholder: float, **extra: Any) -> None:
    """`cost_placeholder_usd` is the cost at the rates in force for the model used (LIVE_PRICE_IN_PER_M and _OUT_PER_M: the list
    prices of that model, set per run); `cost_lower_usd` is the same tokens at the mini-class rates, for comparison."""
    doc = ledger()
    doc["cap_usd"] = CAP_USD
    doc["entries"].append({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "label": label, "kind": kind,
                           "tokens_in": tin, "tokens_out": tout, "cost_placeholder_usd": round(cost_placeholder, 4),
                           "cost_lower_usd": round(tin / 1e6 * LOWER[0] + tout / 1e6 * LOWER[1], 4),
                           "rates_in_out_per_m": list(prices()), "computer_use_model": model_ids().get("computer_use"), **extra})
    doc["spent_placeholder_usd"] = round(sum(e["cost_placeholder_usd"] for e in doc["entries"]), 4)
    doc["spent_lower_usd"] = round(sum(e["cost_lower_usd"] for e in doc["entries"]), 4)
    doc["pct_of_cap"] = round(100 * doc["spent_placeholder_usd"] / CAP_USD, 1)
    RESULTS.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(doc, indent=1))


def live_model(budget: float) -> LiveModel:
    port = get_model_port(fresh=True, ledgered=False)
    if getattr(port, "name", "") == "mock":
        raise SystemExit("refusing to run the LIVE evaluation against the mock model: unset UNDERSTUDY_MOCK")
    left = CAP_USD - spent()
    if left <= 0.25:
        raise SystemExit(f"the live cap of {CAP_USD} USD is used ({spent()} spent); stop and tell the lead")
    return LiveModel(port, data_dir() / "eval" / "live_cache_t3.json", min(budget, left))


async def smoke(site: str, idx: int, budget: float, steps: int, label: str) -> dict[str, Any]:
    h = generate_households(20, 7001)[idx]
    model = live_model(budget)
    tin0, tout0 = model.tokens()
    root = data_dir() / "eval" / "scratch_t3"
    root.mkdir(parents=True, exist_ok=True)
    audit = AuditLog(root / "audit.jsonl")
    queue = ApprovalQueue(root / "queue", audit=audit)
    events: list[Any] = []
    out: dict[str, Any] = {"label": label, "site": site, "household": h.id, "archetype": h.archetype}
    t0 = time.monotonic()
    with SandboxCluster(ephemeral=True) as cluster:
        async with BrowserHost() as host:
            ctx = await host.new_context()
            guard = Guard(model, run_id=f"r_{label}", mode="model_driven", audit=audit, queue=queue, denylist=Denylist(),
                          recorded_hosts=frozenset(host_key(u) for u in cluster.urls.values()))
            nav = Navigator(f"nav-{site}", context=ctx, model=model, guard=guard, base_url=cluster.urls[site], emit=events.append,
                            use_tier1=False, start_tier=3, allow_tier3=True, defer_cliff=True, t3_max_steps=steps, stall_limit=10)
            err = ""
            try:
                res = await nav.run(CalculatorJob(site, h.params()))
                out.update(state=res.state, amount_ok=(res.value is not None))
            except BudgetExceeded as exc:
                err = f"budget:{exc}"
            except Exception as exc:  # noqa: BLE001 - recorded, not hidden
                err = f"{type(exc).__name__}"
            out["error"] = err
            out["tier3"] = nav.t3_runs
            out["refusals"] = nav.refusals
            out["actions"] = [[e.step, e.action, e.ok, str(e.detail)[:50]] for e in events][:80]
    tin, tout = model.tokens()
    cost = model.cost()
    out.update(wall_s=round(time.monotonic() - t0, 1), tokens_in=tin - tin0, tokens_out=tout - tout0,
               cost_placeholder_usd=round(cost, 4), live_calls=model.calls["live"], budget_truncated=model.blocked > 0)
    record(label, "smoke", tin - tin0, tout - tout0, cost, site=site, household=h.id)
    model.save()
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"{label}.json").write_text(json.dumps(out, indent=1))
    return out


async def dev_round(n: int, seed: int, condition: str, steps: int, budget: float, label: str) -> dict[str, Any]:
    model = live_model(budget)
    root = data_dir() / "eval" / "scratch_t3"
    root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    dropped: list[str] = []
    with SandboxCluster(ephemeral=True) as cluster:
        for i, h in enumerate(generate_households(20, seed)[:n]):
            sw = switch_for(condition, i) if condition != "clean" else {}
            cluster.state.reset()
            audit = AuditLog(root / f"audit_{label}.jsonl")
            queue = ApprovalQueue(root / f"queue_{label}_{i}", audit=audit)
            run_id = f"r_{label}_{h.id}"
            tin0, tout0, cost0, blocked0 = *model.tokens(), model.cost(), model.blocked
            opts = RunOptions(denylist=Denylist(), use_tier1=False, allow_tier3=True, start_tier=3, t3_max_steps=steps,
                              deadline_s=900.0, screenshots=False, query=sw)
            run = BenefitsRun(run_id, h, model=model, base_urls=cluster.urls, queue=queue, audit=audit, options=opts)
            t0 = time.monotonic()
            try:
                res = (await asyncio.wait_for(run.execute(), 900.0)).as_dict()
                err = ""
            except asyncio.TimeoutError:
                res, err = {"state": "failed", "results": {}, "completion": {"ok": False}}, "timeout"
            ok, detail = code_check(h, res)
            tin1, tout1 = model.tokens()
            t3 = [r for nv in run.navigator_objs.values() for r in nv.t3_runs]
            # a false claim is a claimed success that code refused: the run said done and the check fails, or a navigator's Done
            # was not verified (a navigator whose verified claim stands is not a false claim just because another navigator failed)
            claimed = res.get("state") == "done" or any(r.get("false_claim") for r in t3)
            row = {"run_id": run_id, "household": h.id, "archetype": h.archetype, "condition": condition, "switches": sw,
                   "state": res.get("state"), "reason": str(res.get("reason", ""))[:120], "code_check_ok": ok,
                   "claimed_success": claimed, "false_claim": bool(claimed and not ok), "figures_match": detail["figures_match"],
                   "awaiting_approval": bool(res.get("awaiting_approval")), "submissions": len(cluster.state.submissions),
                   "steps": sum(1 for e in run.events if e.get("event") == "step"), "tier3": [{k: v for k, v in r.items() if k != "prompt_chars"} for r in t3],
                   "refusals": sum(r.get("refusals", 0) for r in t3), "wall_s": round(time.monotonic() - t0, 1), "error": err,
                   "tokens_in": tin1 - tin0, "tokens_out": tout1 - tout0, "cost_placeholder_usd": round(model.cost() - cost0, 4),
                   "budget_truncated": model.blocked > blocked0}
            if row["budget_truncated"]:
                dropped.append(run_id)                      # cut short by the guard: not a result
                print(f"{run_id}: DISCARDED, the budget guard cut it short", flush=True)
                break
            rows.append(row)
            record(label, "dev_round", tin1 - tin0, tout1 - tout0, model.cost() - cost0, household=h.id)
            model.save()
            print(f"{run_id}: ok={ok} state={row['state']} claimed={claimed} false_claim={row['false_claim']} steps={row['steps']} "
                  f"refusals={row['refusals']} {row['wall_s']}s ~${spent():.2f} of {CAP_USD}", flush=True)
            if spent() >= 0.8 * CAP_USD:
                print("STOP: 80 percent of the live cap is spent; tell the lead before going on", flush=True)
                break
    n_ok = sum(1 for r in rows if r["code_check_ok"])
    doc = {"label": label, "in_sample": True, "models": model_ids(), "rates_in_out_per_m": list(prices()), "seed": seed,
           "condition": condition, "n": len(rows), "n_ok": n_ok,
           "false_claims": sum(1 for r in rows if r["false_claim"]), "dropped": dropped, "rows": rows,
           "spent_placeholder_usd": spent()}
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"{label}.json").write_text(json.dumps(doc, indent=1))
    return doc


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("smoke")
    a.add_argument("--site", default="b", choices=["a", "b", "c"])
    a.add_argument("--household", type=int, default=1)
    a.add_argument("--budget", type=float, default=1.0)
    a.add_argument("--steps", type=int, default=40)
    a.add_argument("--label", default="diag_smoke")
    b = sub.add_parser("round")
    b.add_argument("--households", type=int, default=10)
    b.add_argument("--seed", type=int, default=7001)
    b.add_argument("--condition", default="clean")
    b.add_argument("--steps", type=int, default=200)
    b.add_argument("--budget", type=float, default=4.0)
    b.add_argument("--label", required=True)
    args = ap.parse_args()
    if args.cmd == "smoke":
        out = asyncio.run(smoke(args.site, args.household, args.budget, args.steps, args.label))
    else:
        out = asyncio.run(dev_round(args.households, args.seed, args.condition, args.steps, args.budget, args.label))
    print(json.dumps({k: v for k, v in out.items() if k not in ("rows", "actions")}, indent=1)[:3000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
