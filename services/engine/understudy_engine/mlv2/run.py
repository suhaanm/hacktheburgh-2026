"""CLI for the v2 evaluation runs (PLAN.md section 5).

  python -m understudy_engine.mlv2.run dev [--pools D0,DEV]       dev numbers (debugging and the primary-candidate rule); writes results/dev_*.json
  python -m understudy_engine.mlv2.run freeze                     records the dev-picked primary candidates and the code hashes in results/frozen.json
  UNDERSTUDY_MLV2_HELDOUT=1 python -m understudy_engine.mlv2.run heldout --part hazard    the single frozen held-out run of one part

The held-out command refuses without the token, without frozen.json, or when the part already has a ``start`` line in heldout_log.jsonl.
"""
from __future__ import annotations

import argparse
import sys

from understudy_engine.mlv2 import freeze


PART_POOL = {"hazard": "HELD", "genome": "APP-HELD", "mismatch": "MIS-HELD"}      # the held-out pool each part reads (one name per generator family)


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def cmd_dev(args) -> int:
    if args.part == "genome":
        from understudy_engine.mlv2.genome_part import run_genome_part

        for pool in [p.strip() for p in args.pools.split(",") if p.strip()]:
            res = run_genome_part(pool, frozen=None, n_boot=args.n_boot, log=_log)
            res["split_label"] = "dev"
            freeze.write_json(freeze.out_dir() / "results" / f"dev_genome_{pool.lower()}.json", res)
            _log(f"wrote dev_genome_{pool.lower()}.json")
        return 0
    if args.part == "mismatch":
        from understudy_engine.mlv2.mismatch import run_mismatch_part

        roles = tuple(r.strip() for r in args.roles.split(",") if r.strip())
        res = run_mismatch_part("MIS-DEV", frozen=freeze.read_frozen(), roles=roles, n_boot=args.n_boot, log=_log)
        res["split_label"] = "dev"
        freeze.write_json(freeze.out_dir() / "results" / "dev_mismatch.json", res)
        _log("wrote dev_mismatch.json")
        return 0
    from understudy_engine.mlv2.hazard_part import run_hazard_part

    for pool in [p.strip() for p in args.pools.split(",") if p.strip()]:
        full = pool != "D0"
        res = run_hazard_part(pool, frozen=None, fast=False, n_boot=args.n_boot, with_ablation=full and not args.no_ablation, with_controls=True,
                              log=_log)
        res["split_label"] = "dev"
        freeze.write_json(freeze.out_dir() / "results" / f"dev_hazard_{pool.lower()}.json", res)
        _log(f"wrote dev_hazard_{pool.lower()}.json")
    return 0


def cmd_freeze(args) -> int:
    """Two stages. ``plan``: the choices the PLAN fixed without data (C1, E4, Q1) so the genome part can run. ``hazard``: the family A primary and A7's base
    from the DEV rule (section 6.2), needed by the hazard and mismatch parts and by the transfer test."""
    cur = freeze.read_frozen() or {}
    if args.stage == "plan":
        cur.update({"primary_c": "C1", "primary_e": "E4", "primary_q": "Q1", "plan_stage_frozen_at": freeze.now()})
        cur.setdefault("hazard_frozen", False)
        cur["note"] = ("primary_c, primary_e, primary_q are fixed by PLAN.md, not by data. primary_a and a7_base come from the DEV rule in section 6.2 "
                       "and are frozen by the `hazard` stage before any held-out hazard, mismatch or transfer run.")
        freeze.write_json(freeze.frozen_path(), cur)
        _log("frozen (plan stage): primary_c=C1 primary_e=E4 primary_q=Q1")
        return 0
    d = freeze.read_json(freeze.out_dir() / "results" / "dev_hazard_dev.json")
    primary = d["dev_primary_rule_result"]
    a7 = d["dev_a7_base"]
    hashes = freeze.code_hashes("hazard")
    cur.update({
        "frozen_at": freeze.now(), "hazard_frozen": True, "a7_base": a7, "primary_a_dev_rule": primary,
        "primary_a": ("A7" if (primary or "").startswith("A7") else primary), "primary_c": "C1", "primary_e": "E4", "primary_q": "Q1",
        "hazard_code_fingerprint": freeze.code_fingerprint(hashes), "hazard_code_hashes": hashes,
        "note": "Chosen by the DEV rule in PLAN.md section 6.2 before any held-out hazard run. primary_a None means no candidate qualified on DEV.",
    })
    freeze.write_json(freeze.frozen_path(), cur)
    _log(f"frozen (hazard stage): primary_a={cur['primary_a']} a7_base={a7}")
    return 0


def cmd_transfer(args) -> int:
    """M5: score models trained on synthetic personas only (DEV pool) on the finished simulated participants. Read-only on evals/study_sim.
    Run it only after the lead confirms the simulated study has finished; nothing here is tuned on those traces."""
    from understudy_engine.hazard.features import build_bins
    from understudy_engine.mlv2 import splits, transfer

    frozen = freeze.read_frozen()
    if frozen is None:
        _log("refused: results/frozen.json is missing; run `freeze` first (no model may be chosen after seeing simulated-participant numbers)")
        return 3
    prim = frozen.get("primary_a")
    spec_id = None if not prim else (frozen["a7_base"] if prim == "A7" else prim)
    sim = transfer.load_sim(args.results_dir)
    train_tab = build_bins(splits.load_pool("DEV"))
    res = transfer.evaluate_transfer(train_tab, sim, primary_spec_id=spec_id, n_boot=args.n_boot)
    res["frozen"] = {k: frozen.get(k) for k in ("a7_base", "primary_a", "frozen_at")}
    res["finished_participants"] = sim.finished
    freeze.write_json(freeze.out_dir() / "results" / "transfer_sim.json", res)
    _log(f"wrote transfer_sim.json (n finished = {len(sim.finished)})")
    return 0


def cmd_heldout(args) -> int:
    part = args.part
    if part not in freeze.PARTS:
        _log(f"unknown part {part}; choose from {freeze.PARTS}")
        return 2
    if not freeze.token_ok():
        _log(f"refused: set {freeze.HELDOUT_TOKEN_ENV}=1 (single frozen run, see evals/mlv2/PLAN.md section 5)")
        return 3
    frozen = freeze.read_frozen()
    if frozen is None:
        _log("refused: results/frozen.json is missing; run `freeze` first")
        return 3
    if part in ("hazard", "mismatch") and not frozen.get("hazard_frozen"):
        _log("refused: the hazard stage of the freeze has not been run (primary_a comes from the DEV rule)")
        return 3
    if freeze.part_started(part) and not args.amended:
        _log(f"refused: part {part} already has a start line in heldout_log.jsonl (a declared amendment is needed to run it again)")
        return 3
    hashes = freeze.code_hashes(part)
    freeze.append_log({"event": "start", "part": part, "t": freeze.now(), "code_fingerprint": freeze.code_fingerprint(hashes), "code_hashes": hashes,
                       "frozen": {k: frozen.get(k) for k in ("a7_base", "primary_a", "primary_c", "primary_e", "primary_q")}})
    if part == "hazard":
        from understudy_engine.mlv2.hazard_part import run_hazard_part

        res = run_hazard_part(PART_POOL["hazard"], frozen=frozen, fast=False, n_boot=args.n_boot, log=_log)
    elif part == "genome":
        from understudy_engine.mlv2.genome_part import run_genome_part

        res = run_genome_part(PART_POOL["genome"], frozen=frozen, n_boot=args.n_boot, log=_log)
    else:
        from understudy_engine.mlv2.mismatch import run_mismatch_part

        res = run_mismatch_part(PART_POOL["mismatch"], frozen=frozen, n_boot=args.n_boot, log=_log)
    res["split_label"] = "held-out (single frozen run)"
    res["code_fingerprint"] = freeze.code_fingerprint(hashes)
    res["frozen"] = {k: frozen.get(k) for k in ("a7_base", "primary_a", "primary_c", "primary_e", "primary_q", "frozen_at")}
    freeze.write_json(freeze.out_dir() / "results" / f"heldout_{part}.json", res)
    freeze.append_log({"event": "done", "part": part, "t": freeze.now(), "seconds": res.get("seconds")})
    _log(f"wrote heldout_{part}.json")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m understudy_engine.mlv2.run")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dev")
    d.add_argument("--part", default="hazard", choices=("hazard", "genome", "mismatch"))
    d.add_argument("--pools", default="D0,DEV")
    d.add_argument("--roles", default="benefits-processor,data-analyst,programmer")
    d.add_argument("--n-boot", type=int, default=4000)
    d.add_argument("--no-ablation", action="store_true")
    d.set_defaults(fn=cmd_dev)
    f = sub.add_parser("freeze")
    f.add_argument("--stage", default="hazard", choices=("plan", "hazard"))
    f.set_defaults(fn=cmd_freeze)
    t = sub.add_parser("transfer")
    t.add_argument("--results-dir", default=None)
    t.add_argument("--n-boot", type=int, default=4000)
    t.set_defaults(fn=cmd_transfer)
    h = sub.add_parser("heldout")
    h.add_argument("--part", required=True)
    h.add_argument("--n-boot", type=int, default=4000)
    h.add_argument("--amended", action="store_true", help="only after a dated amendment in PLAN.md declares a re-run")
    h.set_defaults(fn=cmd_heldout)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
