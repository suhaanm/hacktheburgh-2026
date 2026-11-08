"""CLI for the decision-value follow-up (``evals/hrt/PLAN_VALUE.md``).

  python -m understudy_engine.hrt.run_value dev                                  DEV pool (k = 69, 70) only; writes evals/hrt/results/dev_value.json
  python -m understudy_engine.hrt.run_value freeze                               hashes the part's code and plan into results/frozen.json
  UNDERSTUDY_HRT_HELDOUT=1 python -m understudy_engine.hrt.run_value heldout    the single frozen run on the new seeds (k = 61 to 68)

The held-out command refuses without the token, without a freeze of part ``value``, after any change to its code or plan, or on a second run.
"""
from __future__ import annotations

import argparse
import sys
import time
from typing import Any

from . import freeze as fz
from . import value as vl
from . import worlds as wd

PART = "value"


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def run_value_part(split: str, *, log=_log) -> dict[str, Any]:
    from . import prospective as pr

    held = split == "held"
    B = 2000 if held else 300
    ks = vl.HELD_K if held else vl.DEV_K
    t0 = time.time()
    dep = pr.fit_deployed(wd.train_episodes())
    worlds: dict[str, Any] = {}
    worlds["v1"] = vl.run_world("v1", dep, [(f"v1v-{k}", wd.v1_deployment_episodes(k)) for k in ks], B=B, seed=0, log=log)
    for fam in wd.FAMILIES:
        worlds[fam] = vl.run_world(fam, dep, [(f"{fam}v-{k}", wd.v2_deployment_episodes(fam, k)) for k in ks], B=B, seed=0, log=log)
    return {"split_label": "held-out (single frozen run)" if held else "dev", "origin": "synthetic", "worlds": worlds, "claims": vl.judge_value(worlds),
            "design": {"s_minutes": vl.S_MIN, "a_minutes": vl.A_MIN, "threshold": vl.threshold(vl.A_MIN), "a_grid": list(vl.A_GRID), "origins_per_hour": vl.ORIGINS_PER_HOUR,
                       "deployments": list(ks), "bootstrap_B": B}, "seconds": round(time.time() - t0, 1)}


def cmd_dev(args) -> int:
    res = run_value_part("dev")
    fz.write_json(fz.out_dir() / "results" / "dev_value.json", res)
    _log(f"wrote dev_value.json ({res['seconds']} s)")
    return 0


def cmd_freeze(args) -> int:
    cur = fz.freeze((PART,))
    _log(f"frozen {PART}: {cur['parts'][PART]['fingerprint'][:16]}")
    return 0


def cmd_heldout(args) -> int:
    try:
        hs = fz.check_can_run_heldout(PART, amended=args.amended)
    except fz.Refused as e:
        _log(f"refused: {e}")
        return 3
    fz.append_log({"event": "start", "part": PART, "t": fz.now(), "fingerprint": fz.fingerprint(hs), "code_hashes": hs})
    res = run_value_part("held")
    res["code_fingerprint"] = fz.fingerprint(hs)
    fz.write_json(fz.out_dir() / "results" / f"heldout_{PART}.json", res)
    fz.append_log({"event": "done", "part": PART, "t": fz.now(), "seconds": res["seconds"]})
    _log(f"wrote heldout_{PART}.json ({res['seconds']} s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m understudy_engine.hrt.run_value")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("dev").set_defaults(fn=cmd_dev)
    sub.add_parser("freeze").set_defaults(fn=cmd_freeze)
    h = sub.add_parser("heldout")
    h.add_argument("--amended", action="store_true", help="only after a dated amendment in PLAN_VALUE.md declares a re-run")
    h.set_defaults(fn=cmd_heldout)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
