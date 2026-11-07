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
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import Any

from .audit import AuditLog
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
            "amounts": {site: r.get("amount") for site, r in sorted(res.results.items())}}


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
            "submissions_without_approval": sum(r["submissions"] for r in rows), "steps_total": steps,
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
    return {"suite": "LH-2", "offline_double": True, "pause_latency_s": round(latency, 3), "pauses": gate.pauses,
            "steps_run_while_paused": int(marks["steps_while_paused"] - marks["steps_at_signal"]),
            "steps_after_resume": int(steps_after), "steps_remaining_in_baseline": int(remaining),
            "result_equals_uninterrupted": cut["amounts"] == base["amounts"], "ok": ok, "baseline": base, "interrupted": cut}


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
                     "state": r["state"], "steps": r["steps"], "false_claims": r["false_claims"], "ok": ok})
    return {"suite": "LH-3", "offline_double": True, "faults": len(rows), "recovered": sum(1 for r in rows if r["recovered"]),
            "escalated": sum(1 for r in rows if r["escalated"]), "crashes": sum(1 for r in rows if r["crashed"]),
            "false_claims": sum(r["false_claims"] for r in rows), "ok": all(r["ok"] for r in rows), "rows": rows}


async def main_async(n: int, out: Path | None, which: list[str]) -> dict[str, Any]:
    import tempfile

    root = Path(tempfile.mkdtemp(prefix="lh-suite-"))
    import os

    os.environ.setdefault("UNDERSTUDY_DATA_DIR", str(root / "data"))
    doc: dict[str, Any] = {"note": "offline, grounded test double: tests the code, not any model", "suites": {}}
    with SandboxCluster(ephemeral=True) as cluster:
        if "1" in which:
            doc["suites"]["LH-1"] = await lh1(cluster, root, n=n)
        if "2" in which:
            doc["suites"]["LH-2"] = await lh2(cluster, root)
        if "3" in which:
            doc["suites"]["LH-3"] = await lh3(cluster, root)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(doc, indent=1))
    return doc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--only", default="123")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    doc = asyncio.run(main_async(a.n, Path(a.out) if a.out else None, list(a.only)))
    for k, v in doc["suites"].items():
        print(k, "ok" if v["ok"] else "FAIL", {x: y for x, y in v.items() if x not in ("rows", "baseline", "interrupted")})
    return 0 if all(v["ok"] for v in doc["suites"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
