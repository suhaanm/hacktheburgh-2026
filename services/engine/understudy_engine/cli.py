"""``understudy`` command line.

    understudy synth --all                 regenerate every synthetic dataset (deterministic)
    understudy synth --persona night-owl   one persona; --apprentices for the benefits-task traces
    understudy pack validate [PATH ...]    validate role packs (ROL-1)
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
    from .personas import apprentices
    from .store.paths import data_dir

    root = Path(args.out) if args.out else data_dir()
    t0 = time.time()
    slugs = list(PERSONA_BY_SLUG) if args.all or not (args.persona or args.apprentices) else args.persona
    want_apprentices = args.all or args.apprentices or not args.persona
    for slug in slugs or []:
        if slug not in PERSONA_BY_SLUG:
            print(f"unknown persona {slug!r}; choose from {', '.join(PERSONA_BY_SLUG)}", file=sys.stderr)
            return 2
        r = write_persona(PERSONA_BY_SLUG[slug], root, with_mc=not args.fast)
        print(f"persona {slug}: {r['events']} events -> {r['dir']}")
    if want_apprentices:
        r = apprentices.generate(root)
        print(f"apprentices: {r['events']} events, {r['traces']} traces -> {r['dir']}")
    print(f"done in {time.time() - t0:.1f}s (synthetic, seeded, deterministic)")
    return 0


def _pack(args: argparse.Namespace) -> int:
    try:
        from .packs.cli import validate_command
    except ImportError:  # pragma: no cover - packs land in E2
        print("pack validation is not available yet", file=sys.stderr)
        return 3
    return validate_command(args.paths)


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    port = int(args.port or os.environ.get("ENGINE_PORT", "7700"))
    uvicorn.run("understudy_engine.api.app:app", host=args.host, port=port, log_level="info")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="understudy", description="Understudy engine tools")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("synth", help="generate synthetic personas and apprentices")
    p.add_argument("--all", action="store_true", help="all four personas plus the apprentices")
    p.add_argument("--persona", action="append", help="persona slug (repeatable)")
    p.add_argument("--apprentices", action="store_true", help="benefits-task apprentice traces")
    p.add_argument("--out", help="data root (default: UNDERSTUDY_DATA_DIR or <repo>/data)")
    p.add_argument("--fast", action="store_true", help="skip the Monte Carlo expectation in truth.json")
    p.set_defaults(fn=_synth)

    p = sub.add_parser("pack", help="role pack tools")
    psub = p.add_subparsers(dest="pack_cmd", required=True)
    pv = psub.add_parser("validate", help="validate role packs against the pack schema")
    pv.add_argument("paths", nargs="*", help="pack directories (default: every pack under packages/packs)")
    pv.set_defaults(fn=_pack)

    p = sub.add_parser("serve", help="run the engine API")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", default=None)
    p.set_defaults(fn=_serve)

    args = parser.parse_args(argv)
    return int(args.fn(args) or 0)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
