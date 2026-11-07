"""Run the benefits workflow on N generated households and score it against the oracle (AGT-5, AGT-6).

    uv run python -m understudy_agent.benefits_eval --n 20            # writes data/eval/agent_benefits_<n>.json
    uv run python -m understudy_agent.benefits_eval --golden          # records the cached golden run (AGT-8)

Everything is synthetic and runs on the local sandbox sites with the deterministic mock model. Evidence, the
approval queue and the audit log go to a scratch directory (data/eval/scratch), not the real queue.

A household PASSES only if all of these hold, each decided by code:
  * every calculator's extracted figure equals what that site is documented to display;
  * the reconciliation flags a discrepancy exactly when the sites disagree with each other;
  * if the sites agree, the reconciled figure is within 1 pound of the oracle; if they disagree, the run
    flagged it (a flagged discrepancy is the correct behaviour, so it is not an oracle miss);
  * the completion check passed (each result's fields and the note id are on the final page);
  * the cliff check was done on all three calculators;
  * nothing was submitted and one approval item is waiting.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

from understudy_engine.trust.stats import wilson_interval

from . import golden
from .audit import AuditLog
from .models import get_model_port
from .orchestrator import BenefitsRun, RunOptions
from .queue import ApprovalQueue
from .sandbox_sites.households import Household, generate_households
from .sandbox_sites.oracle import TOLERANCE_GBP, cliff_flags, disagreements, score, site_expected
from .sandbox_sites.runner import SandboxCluster
from .security.denylist import Denylist
from .supervisor import data_dir
from .tiers.heuristic import HeuristicModelPort


def judge(h: Household, res: dict[str, Any], submissions: int) -> dict[str, Any]:
    exp = {s: site_expected(s, h) for s in "abc"}
    ora = score(h)
    got = res.get("results", {})
    extraction = {s: (s in got and abs(got[s]["amount"] - exp[s]["uc_monthly"]) <= 0.06) for s in "abc"}
    amounts = [exp[s]["uc_monthly"] for s in "abc"]
    elig = {exp[s]["eligible"] for s in "abc"}
    sites_agree = (max(amounts) - min(amounts) <= TOLERANCE_GBP) and len(elig) == 1
    recon = res.get("reconciliation") or {}
    flagged = recon.get("status") == "discrepancy"
    reconcile_ok = bool(recon) and (flagged == (not sites_agree))
    if flagged:
        oracle_ok = True  # flagging a disagreement is the correct outcome
    else:
        oracle_ok = bool(recon) and abs(recon.get("value", 1e9) - ora["uc_monthly"]) <= TOLERANCE_GBP
    checks = {
        "extraction": all(extraction.values()),
        "reconcile": reconcile_ok,
        "oracle_or_flagged": oracle_ok,
        "completion": bool(res.get("completion", {}).get("ok")),
        "cliff_checks": all(res.get("cliff_checked", {}).get(s) for s in "abc"),
        "stopped_before_submit": submissions == 0 and bool(res.get("awaiting_approval")),
        "no_false_claims": res.get("false_claims", 1) == 0,
    }
    return {
        "household_id": h.id, "archetype": h.archetype, "cliff_flags": cliff_flags(h),
        "oracle_uc": ora["uc_monthly"], "site_expected": {s: exp[s]["uc_monthly"] for s in "abc"},
        "extracted": {s: got.get(s, {}).get("amount") for s in "abc"},
        "sites_off_vs_oracle": disagreements(h)["off_by"], "flagged_discrepancy": flagged,
        "checks": checks, "pass": all(checks.values()), "state": res.get("state"),
        "tiers": sorted({e["tier"] for e in res.get("tier_log", [])}), "steps": len(res.get("tier_log", [])),
        "elapsed_s": res.get("elapsed_s"),
    }


async def evaluate(n: int = 20, seed: int = 2026, *, switches_for: dict[str, dict[str, str]] | None = None,
                   root: Path | None = None, label: str = "clean") -> dict[str, Any]:
    root = root or (data_dir() / "eval" / "scratch")
    root.mkdir(parents=True, exist_ok=True)
    old_env = os.environ.get("UNDERSTUDY_DATA_DIR")
    os.environ["UNDERSTUDY_DATA_DIR"] = str(root)
    rows: list[dict[str, Any]] = []
    t0 = time.time()
    try:
        audit = AuditLog(root / "audit.jsonl")
        queue = ApprovalQueue(root / "queue", audit=audit)
        with SandboxCluster(ephemeral=True) as cluster:
            for h in generate_households(n, seed):
                cluster.state.reset()
                model = HeuristicModelPort(get_model_port(mock=True, fresh=True))
                opts = RunOptions(denylist=Denylist(), query=(switches_for or {}).get(h.id, {}))
                run = BenefitsRun(f"r_eval_{h.id}", h, model=model, base_urls=cluster.urls, queue=queue, audit=audit,
                                  options=opts)
                res = (await run.execute()).as_dict()
                row = judge(h, res, len(cluster.state.submissions))
                row["cliff_opens_recorded"] = len(cluster.state.cliff_opens)
                rows.append(row)
    finally:
        if old_env is None:
            os.environ.pop("UNDERSTUDY_DATA_DIR", None)
        else:
            os.environ["UNDERSTUDY_DATA_DIR"] = old_env
    k = sum(1 for r in rows if r["pass"])
    lo, hi = wilson_interval(k, len(rows))
    flagged = [r for r in rows if r["flagged_discrepancy"]]
    out = {
        "meta": {"origin": "synthetic", "n": len(rows), "n_unit": "households", "split": None, "interval_level": 0.95,
                 "note": "Local sandbox calculators, deterministic mock model, simplified internal oracle (not law).",
                 "label": label, "seed": seed, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
        "pass_rate": {"passed": k, "n": len(rows), "rate": round(k / max(1, len(rows)), 4),
                      "wilson_95": [round(lo, 3), round(hi, 3)]},
        "check_pass_counts": {name: sum(1 for r in rows if r["checks"][name]) for name in rows[0]["checks"]} if rows else {},
        "flagged_discrepancies": {"count": len(flagged), "households": [r["household_id"] for r in flagged]},
        "sites_vs_oracle_disagreements": [{"household": r["household_id"], "archetype": r["archetype"],
                                           "off_by": r["sites_off_vs_oracle"], "flagged": r["flagged_discrepancy"]}
                                          for r in rows if r["sites_off_vs_oracle"]],
        "tiers_seen": sorted({t for r in rows for t in r["tiers"]}),
        "mean_elapsed_s": round(sum(r["elapsed_s"] or 0 for r in rows) / max(1, len(rows)), 2),
        "wall_s": round(time.time() - t0, 1),
        "rows": rows,
    }
    return out


async def record_golden(hid_index: int = 3) -> Path:
    """One mock run on the discrepancy household, saved as the cached golden run. The run itself happens in a
    scratch directory so no approval item is left in the real queue."""
    h = generate_households(20)[hid_index]
    root = data_dir() / "eval" / "scratch_golden"
    root.mkdir(parents=True, exist_ok=True)
    old = os.environ.get("UNDERSTUDY_DATA_DIR")
    real = data_dir()
    os.environ["UNDERSTUDY_DATA_DIR"] = str(root)
    try:
        audit = AuditLog(root / "audit.jsonl")
        queue = ApprovalQueue(root / "queue", audit=audit)
        with SandboxCluster(ephemeral=True) as cluster:
            model = HeuristicModelPort(get_model_port(mock=True, fresh=True))
            run = BenefitsRun(f"r_golden_{h.id}", h, model=model, base_urls=cluster.urls, queue=queue, audit=audit,
                              options=RunOptions(denylist=Denylist()))
            res = (await run.execute()).as_dict()
        if res["state"] != "done":
            raise SystemExit(f"golden run did not finish cleanly: {res['state']} {res.get('reason')}")
        item = queue.get(res["queue_id"])
    finally:
        if old is None:
            os.environ.pop("UNDERSTUDY_DATA_DIR", None)
        else:
            os.environ["UNDERSTUDY_DATA_DIR"] = old
    return golden.save_golden(res, run.events, item, run.run_id, src_root=root) if real else golden.golden_path()


def robust_switches(n: int, seed: int) -> dict[str, dict[str, str]]:
    """Failure injection per household: selectors change on one site, or a site answers 503 once."""
    pats = [{"b": "?layout=v2"}, {"c": "?layout=v2"}, {"a": "?layout=v2", "b": "?glitch=503once"},
            {"c": "?glitch=503once"}]
    return {h.id: pats[i % len(pats)] for i, h in enumerate(generate_households(n, seed))}


def main() -> None:  # pragma: no cover - manual
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--golden", action="store_true")
    ap.add_argument("--robust", action="store_true", help="inject layout changes and one-off 503s (AGT-7)")
    a = ap.parse_args()
    os.environ.setdefault("UNDERSTUDY_MOCK", "1")
    if a.golden:
        print("golden run saved to", asyncio.run(record_golden()))
        return
    sw = robust_switches(a.n, a.seed) if a.robust else None
    out = asyncio.run(evaluate(a.n, a.seed, switches_for=sw, label="robust" if a.robust else "clean",
                               root=data_dir() / "eval" / ("scratch_robust" if a.robust else "scratch")))
    p = data_dir() / "eval" / f"agent_benefits_{a.n}{'_robust' if a.robust else ''}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    pr = out["pass_rate"]
    print(f"pass {pr['passed']}/{pr['n']} (95% Wilson {pr['wilson_95']}), flagged discrepancies "
          f"{out['flagged_discrepancies']['count']}, mean {out['mean_elapsed_s']}s/run, wrote {p}")


if __name__ == "__main__":  # pragma: no cover
    main()
