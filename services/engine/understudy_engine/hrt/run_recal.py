"""CLI for the online-recalibration follow-up (``evals/hrt/PLAN_RECAL.md``).

  python -m understudy_engine.hrt.run_recal dev                                  DEV pool (k = 29, 30) only; writes evals/hrt/results/dev_recal.json
  python -m understudy_engine.hrt.run_recal freeze                               hashes the part's code and plan into results/frozen.json
  UNDERSTUDY_HRT_HELDOUT=1 python -m understudy_engine.hrt.run_recal heldout    the single frozen run on the new seeds (k = 21 to 28)

The held-out command refuses without the token, without a freeze of part ``recal``, after any change to its code or plan, or on a second run.
"""
from __future__ import annotations

import argparse
import sys
import time
from typing import Any

from . import freeze as fz
from . import recal as rc
from . import worlds as wd

PART = "recal"


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def run_recal_part(split: str, *, log=_log) -> dict[str, Any]:
    from . import prospective as pr

    held = split == "held"
    B, cal = (2000, 500) if held else (300, 60)
    ks = rc.RECAL_K if held else rc.DEV_K
    t0 = time.time()
    dep = pr.fit_deployed(wd.train_episodes())
    worlds: dict[str, Any] = {}
    worlds["v1"] = rc.run_hazard_world_recal("v1", dep, [(f"v1r-{k}", wd.v1_deployment_episodes(k)) for k in ks], B=B, seed=0, cal_draws=cal, log=log)
    for fam in wd.FAMILIES:
        worlds[fam] = rc.run_hazard_world_recal(fam, dep, [(f"{fam}r-{k}", wd.v2_deployment_episodes(fam, k)) for k in ks], B=B, seed=0, cal_draws=cal, log=log)
    model, base = pr.fit_error_model()
    worlds["route_no_drift"] = rc.run_error_world_recal("route_no_drift", model, base, ks, drift=False, B=B, seed=0, cal_draws=cal, log=log)
    worlds["route_drift"] = rc.run_error_world_recal("route_drift", model, base, ks, drift=True, B=B, seed=0, cal_draws=cal, log=log)
    return {"split_label": "held-out (single frozen run)" if held else "dev", "origin": "synthetic", "worlds": worlds, "claims": rc.judge_recal(worlds),
            "design": {"ridge": rc.RIDGE, "refit_every": rc.REFIT_EVERY, "deployments": list(ks), "bootstrap_B": B, "calibration_draws": cal}, "seconds": round(time.time() - t0, 1)}


def cmd_dev(args) -> int:
    res = run_recal_part("dev")
    fz.write_json(fz.out_dir() / "results" / "dev_recal.json", res)
    _log(f"wrote dev_recal.json ({res['seconds']} s)")
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
    res = run_recal_part("held")
    res["code_fingerprint"] = fz.fingerprint(hs)
    fz.write_json(fz.out_dir() / "results" / f"heldout_{PART}.json", res)
    fz.append_log({"event": "done", "part": PART, "t": fz.now(), "seconds": res["seconds"]})
    _log(f"wrote heldout_{PART}.json ({res['seconds']} s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m understudy_engine.hrt.run_recal")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("dev").set_defaults(fn=cmd_dev)
    sub.add_parser("freeze").set_defaults(fn=cmd_freeze)
    h = sub.add_parser("heldout")
    h.add_argument("--amended", action="store_true", help="only after a dated amendment in PLAN_RECAL.md declares a re-run")
    h.set_defaults(fn=cmd_heldout)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
