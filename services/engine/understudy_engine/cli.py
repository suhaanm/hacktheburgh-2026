"""``understudy`` command line.

    understudy synth --all                 regenerate every synthetic dataset (deterministic)
    understudy synth --persona night-owl   one persona; --apprentices, --learners for the benefits-task datasets
    understudy pack validate [PATH ...]    validate role packs (ROL-1)
    understudy plugin validate [PATH ...]  validate marketplace plugin references and manifests (plugins package)
    understudy serve                       run the engine API on ENGINE_PORT (default 7700)
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path


def _synth(args: argparse.Namespace) -> int:
    from .personas import PERSONA_BY_SLUG, write_persona
    from .personas import apprentices, learners
    from .store.paths import data_dir

    root = Path(args.out) if args.out else data_dir()
    t0 = time.time()
    explicit = bool(args.persona or args.apprentices or args.learners)
    slugs = list(PERSONA_BY_SLUG) if args.all or not explicit else (args.persona or [])
    want_apprentices = args.all or args.apprentices or not explicit
    want_learners = args.all or args.learners or not explicit
    for slug in slugs or []:
        if slug not in PERSONA_BY_SLUG:
            print(f"unknown persona {slug!r}; choose from {', '.join(PERSONA_BY_SLUG)}", file=sys.stderr)
            return 2
        r = write_persona(PERSONA_BY_SLUG[slug], root, with_mc=not args.fast)
        print(f"persona {slug}: {r['events']} events -> {r['dir']}")
    if want_apprentices:
        r = apprentices.generate(root)
        print(f"apprentices: {r['events']} events, {r['traces']} traces -> {r['dir']}")
    if want_learners:
        r = learners.generate(root)
        print(f"learners: {r['events']} events, {r['traces']} cases -> {r['dir']}")
    print(f"done in {time.time() - t0:.1f}s (synthetic, seeded, deterministic)")
    return 0


def _pack(args: argparse.Namespace) -> int:
    try:
        from .packs.cli import validate_command
    except ImportError:  # pragma: no cover - packs land in E2
        print("pack validation is not available yet", file=sys.stderr)
        return 3
    return validate_command(args.paths)


def _plugin(args: argparse.Namespace) -> int:
    try:
        from .plugins.cli import validate_command
    except ImportError as exc:       # the plugins package is another track's: a plain message, not a traceback
        print(f"plugin validation is not available: the plugins package is missing or does not import ({exc}).", file=sys.stderr)
        return 2
    return int(validate_command(list(args.paths), quiet=args.quiet) or 0)


def _serve(args: argparse.Namespace) -> int:
    from .api.flags import apply_default_flags

    apply_default_flags()   # D48: the layers are on by default; an explicit UNDERSTUDY_X=0 turns them off
    import uvicorn

    port = int(args.port or os.environ.get("ENGINE_PORT", "7700"))
    os.environ["UNDERSTUDY_ENGINE_LISTEN_PORT"] = str(port)     # the guard's own port; and the proof this engine may speak for the stack
    uvicorn.run("understudy_engine.api.app:app", host=args.host, port=port, log_level="info")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="understudy", description="Understudy engine tools")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("synth", help="generate synthetic personas and apprentices")
    p.add_argument("--all", action="store_true", help="all four personas plus the apprentices")
    p.add_argument("--persona", action="append", help="persona slug (repeatable)")
    p.add_argument("--apprentices", action="store_true", help="benefits-task apprentice traces")
    p.add_argument("--learners", action="store_true", help="three novices over ten days with decaying deficits and coach prompts")
    p.add_argument("--out", help="data root (default: UNDERSTUDY_DATA_DIR or <repo>/data)")
    p.add_argument("--fast", action="store_true", help="skip the Monte Carlo expectation in truth.json")
    p.set_defaults(fn=_synth)

    p = sub.add_parser("pack", help="role pack tools")
    psub = p.add_subparsers(dest="pack_cmd", required=True)
    pv = psub.add_parser("validate", help="validate role packs against the pack schema")
    pv.add_argument("paths", nargs="*", help="pack directories (default: every pack under packages/packs)")
    pv.set_defaults(fn=_pack)

    p = sub.add_parser("plugin", help="marketplace plugin tools")
    plsub = p.add_subparsers(dest="plugin_cmd", required=True)
    plv = plsub.add_parser("validate", help="validate plugin references and manifests")
    plv.add_argument("paths", nargs="*", help="plugin directories or files (default: whatever the plugins package validates by default)")
    plv.add_argument("--quiet", action="store_true", help="print only problems")
    plv.set_defaults(fn=_plugin)

    p = sub.add_parser("serve", help="run the engine API")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", default=None)
    p.set_defaults(fn=_serve)

    args = parser.parse_args(argv)
    return int(args.fn(args) or 0)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
