"""CLI for the HRT evaluation runs (``evals/hrt/PLAN.md`` section 7).

  python -m understudy_engine.hrt.run dev [--part ledger|decisions|all]       DEV pools only; writes evals/hrt/results/dev_<part>.json
  python -m understudy_engine.hrt.run freeze                                  hashes the code and the plan into results/frozen.json
  UNDERSTUDY_HRT_HELDOUT=1 python -m understudy_engine.hrt.run heldout --part ledger|decisions     the single frozen held-out run of one part

Nothing here calls a model, a network or a real account.
"""
from __future__ import annotations

import argparse
import sys
import time
from typing import Any

from . import freeze as fz
from . import worlds as wd


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def run_ledger_part(split: str, *, log=_log) -> dict[str, Any]:
    """Part P: the prospective evaluation of the stuck hazard (v1 world, three shifted worlds) and of error risk (no drift, drift)."""
    from . import prospective as pr

    held = split == "held"
    B, cal = (2000, 500) if held else (300, 60)
    ks_v1 = wd.HELD_K if held else wd.DEV_K
    ks_v2 = wd.HELD_K if held else (1, 2)
    ks_route = wd.ROUTE_HELD_K if held else wd.ROUTE_DEV_K
    t0 = time.time()
    dep = pr.fit_deployed(wd.train_episodes())
    log(f"fitted the deployed models on {dep.n_train_bins} training bins (base rate {dep.base_rate:.3f})")
    v1 = pr.run_hazard_world("v1", dep, [(f"v1-{k}", wd.v1_deployment_episodes(k)) for k in ks_v1], B=B, calibration_draws=cal, log=log)
    shifted = {}
    for fam in wd.FAMILIES:
        shifted[fam] = pr.run_hazard_world(fam, dep, [(f"{fam}-{k}", wd.v2_deployment_episodes(fam, k)) for k in ks_v2], B=B, calibration_draws=cal, log=log)
    model, base = pr.fit_error_model()
    same = pr.run_error_world("route_no_drift", model, base, ks_route, drift=False, B=B, calibration_draws=cal, log=log)
    drift = pr.run_error_world("route_drift", model, base, ks_route, drift=True, B=B, calibration_draws=cal, log=log)
    dtte = pr.fit_deployed_tte(wd.train_episodes())
    tte = pr.run_tte_world(dtte, [(f"v1-{k}", wd.v1_deployment_episodes(k)) for k in ks_v1], B=B, log=log)
    claims = pr.judge_claims(v1, shifted, same, drift, tte)
    return {"split_label": "held-out (single frozen run)" if held else "dev", "origin": "synthetic", "worlds": {"v1": v1, **shifted, "route_no_drift": same, "route_drift": drift}, "tte_v1": tte, "claims": claims,
            "design": {"train": {"pool": "v1 personas, 4 types x replicates " + str(list(wd.TRAIN_K)), "n_bins": dep.n_train_bins, "base_rate": dep.base_rate},
                       "deployments": {"v1": list(ks_v1), "v2": list(ks_v2), "route": list(ks_route)}, "bootstrap_B": B, "calibration_draws": cal,
                       "guard": {"lambda": 0.8, "threshold": 20.0, "B": 4.6, "fallback": "online_base"},
                       "v2": {"people": wd.V2_PEOPLE, "days": wd.V2_DAYS}, "route": {"stream": wd.ROUTE_STREAM_N, "drift_at": wd.ROUTE_DRIFT_AT, "review_lag": wd.REVIEW_LAG}},
            "seconds": round(time.time() - t0, 1)}


def run_decisions_part(split: str, *, log=_log) -> dict[str, Any]:
    from . import scoreboard as sb

    held = split == "held"
    ks = ({"ski": tuple(range(11, 51)), "routing": tuple(range(11, 51)), "presence": wd.HELD_K, "nudge": tuple(range(11, 41))} if held
          else {"ski": wd.DECIDE_DEV_K, "routing": wd.DECIDE_DEV_K, "presence": (1, 2), "nudge": wd.DECIDE_DEV_K})
    t0 = time.time()
    out = sb.evaluate_scoreboard(ks, log=log)
    out.update({"split_label": "held-out (single frozen run)" if held else "dev", "origin": "synthetic", "replicates": {k: len(v) for k, v in ks.items()}, "seconds": round(time.time() - t0, 1)})
    return out


RUNNERS = {"ledger": run_ledger_part, "decisions": run_decisions_part}


def cmd_dev(args) -> int:
    for part in (fz.PARTS if args.part == "all" else (args.part,)):
        res = RUNNERS[part]("dev")
        fz.write_json(fz.out_dir() / "results" / f"dev_{part}.json", res)
        _log(f"wrote dev_{part}.json ({res['seconds']} s)")
    return 0


def cmd_freeze(args) -> int:
    cur = fz.freeze(tuple(fz.PARTS if args.part == "all" else (args.part,)))
    for part, v in cur["parts"].items():
        _log(f"frozen {part}: {v['fingerprint'][:16]}")
    return 0


def cmd_heldout(args) -> int:
    try:
        hs = fz.check_can_run_heldout(args.part, amended=args.amended)
    except fz.Refused as e:
        _log(f"refused: {e}")
        return 3
    fz.append_log({"event": "start", "part": args.part, "t": fz.now(), "fingerprint": fz.fingerprint(hs), "code_hashes": hs})
    res = RUNNERS[args.part]("held")
    res["code_fingerprint"] = fz.fingerprint(hs)
    fz.write_json(fz.out_dir() / "results" / f"heldout_{args.part}.json", res)
    fz.append_log({"event": "done", "part": args.part, "t": fz.now(), "seconds": res["seconds"]})
    _log(f"wrote heldout_{args.part}.json ({res['seconds']} s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m understudy_engine.hrt.run")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dev")
    d.add_argument("--part", default="all", choices=("ledger", "decisions", "all"))
    d.set_defaults(fn=cmd_dev)
    f = sub.add_parser("freeze")
    f.add_argument("--part", default="all", choices=("ledger", "decisions", "all"))
    f.set_defaults(fn=cmd_freeze)
    h = sub.add_parser("heldout")
    h.add_argument("--part", required=True, choices=("ledger", "decisions"))
    h.add_argument("--amended", action="store_true", help="only after a dated amendment in PLAN.md declares a re-run")
    h.set_defaults(fn=cmd_heldout)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
