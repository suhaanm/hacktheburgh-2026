"""CLI for the conformal follow-up (``evals/hrt/PLAN_CONFORMAL.md``).

  python -m understudy_engine.hrt.run_conformal dev                                  DEV pool (k = 35, 36; 52) only; writes evals/hrt/results/dev_conformal.json
  python -m understudy_engine.hrt.run_conformal freeze                               hashes the part's code and plan into results/frozen.json
  UNDERSTUDY_HRT_HELDOUT=1 python -m understudy_engine.hrt.run_conformal heldout    the single frozen run on the new seeds (k = 41 to 48)

The held-out command refuses without the token, without a freeze of part ``conformal``, after any change to its code or plan, or on a second run.
"""
from __future__ import annotations

import argparse
import sys
import time
from typing import Any

from . import conformal as cf
from . import freeze as fz
from . import worlds as wd

PART = "conformal"


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def run_conformal_part(split: str, *, log=_log) -> dict[str, Any]:
    held = split == "held"
    B = 2000 if held else 300
    ks = cf.HELD_K if held else cf.DEV_K
    shift_k = cf.CAL_SHIFT_K if held else cf.DEV_CAL_SHIFT_K
    t0 = time.time()
    models = cf.fit_models(wd.train_episodes())
    cal_pool = cf.concat([cf.origins_for(models, wd.v1_deployment_episodes(k), i) for i, k in enumerate(cf.CAL_K)])
    cal = cf.calibrate(cal_pool, models)
    log(f"  calibrated on {cal['n']}")
    worlds: dict[str, Any] = {}
    worlds["v1"] = cf.run_world("v1", models, [(f"v1c-{k}", wd.v1_deployment_episodes(k)) for k in ks], cal, None, B=B, seed=0, log=log)
    for fam in wd.FAMILIES:
        shift_pool = cf.origins_for(models, wd.v2_deployment_episodes(fam, shift_k), 0)
        worlds[fam] = cf.run_world(fam, models, [(f"{fam}c-{k}", wd.v2_deployment_episodes(fam, k)) for k in ks], cal, cf.calibrate(shift_pool, models), B=B, seed=0, log=log)
    return {"split_label": "held-out (single frozen run)" if held else "dev", "origin": "synthetic", "worlds": worlds, "claims": cf.judge_conformal(worlds),
            "design": {"alpha": cf.ALPHA, "nominal": cf.NOMINAL, "low_coverage_line": cf.LOW_COVERAGE, "ridge": cf.RIDGE, "calibration_k": list(cf.CAL_K), "recalibration_k": shift_k,
                       "deployments": list(ks), "bootstrap_B": B, "calibration": cal["n"]}, "seconds": round(time.time() - t0, 1)}


def cmd_dev(args) -> int:
    res = run_conformal_part("dev")
    fz.write_json(fz.out_dir() / "results" / "dev_conformal.json", res)
    _log(f"wrote dev_conformal.json ({res['seconds']} s)")
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
    res = run_conformal_part("held")
    res["code_fingerprint"] = fz.fingerprint(hs)
    fz.write_json(fz.out_dir() / "results" / f"heldout_{PART}.json", res)
    fz.append_log({"event": "done", "part": PART, "t": fz.now(), "seconds": res["seconds"]})
    _log(f"wrote heldout_{PART}.json ({res['seconds']} s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m understudy_engine.hrt.run_conformal")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("dev").set_defaults(fn=cmd_dev)
    sub.add_parser("freeze").set_defaults(fn=cmd_freeze)
    h = sub.add_parser("heldout")
    h.add_argument("--amended", action="store_true", help="only after a dated amendment in PLAN_CONFORMAL.md declares a re-run")
    h.set_defaults(fn=cmd_heldout)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
