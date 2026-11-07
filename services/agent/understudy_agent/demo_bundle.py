"""Install the demo routine bundle: a canned L1 recording taken through the REAL compile step.

    uv run python -m understudy_agent.demo_bundle install            # data/routines/calc-entry-3x/steps*.json
    uv run python -m understudy_agent.demo_bundle status

For each calculator site the canned recording (sandbox_sites/recordings.py: what the extension would send, no values,
the sensitive "limited capability" field absent) goes through compile.py: schema validation, slot mapping, a dry run
on the sandbox sites (an irreversible step is never executed), and only then is the bundle written. Idempotent: an
identical bundle already on disk is left alone. The dry run uses PRIVATE ephemeral-port copies of the sites (never the shared
sites, never the shared lock), and the saved bundles then point at 7801-7803.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from .compile import compile_and_check, routine_dir, save_bundle
from .models import get_model_port
from .orchestrator import run_async
from .sandbox_sites.households import generate_households
from .sandbox_sites.recordings import synthetic_recording
from .sandbox_sites.runner import SandboxCluster
from .sandbox_sites.specs import SITE_IDS, site_base_urls
from .supervisor import data_dir as default_data_dir
from .tiers.browser import BrowserHost
from .tiers.heuristic import HeuristicModelPort

ROUTINE_ID = "calc-entry-3x"
FILES = {"a": "steps.json", "b": "steps.b.json", "c": "steps.c.json"}


def _digest(b: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(b, sort_keys=True).encode()).hexdigest()[:12]


def _sites_up(urls: dict[str, str]) -> bool:
    try:
        return httpx.get(urls["a"] + "/healthz", timeout=0.6).status_code == 200
    except Exception:  # noqa: BLE001
        return False


def _retarget(bundle: dict[str, Any], dry_base: str, target_base: str) -> dict[str, Any]:
    """The dry run used a private copy of the sites; the saved bundle points at the real ones."""
    out = json.loads(json.dumps(bundle))
    for st in out["steps"]:
        if st.get("op") == "goto" and str(st.get("url", "")).startswith(dry_base):
            st["url"] = target_base + st["url"][len(dry_base):]
    return out


def install_report(routine_id: str = ROUTINE_ID, data_dir: Path | None = None, *,
                   base_urls: dict[str, str] | None = None, log: Any = print) -> dict[str, Any]:
    """Compile and write the bundles. `base_urls` are the sites the bundles will RUN against (default 7801-7803).
    The dry run always uses PRIVATE ephemeral-port copies of the sites and never the shared lock, so seeding works at
    any time, in tests, and while other agents are using the shared sites."""
    root = Path(data_dir) if data_dir else default_data_dir()
    target = base_urls or site_base_urls()
    model = HeuristicModelPort(get_model_port(mock=True, fresh=True))
    household = generate_households(20)[3]   # the 16,000 savings cliff household: a rich dry run
    out: dict[str, Any] = {"paths": [], "actions": {}, "reports": {}}

    async def go(dry_urls: dict[str, str]) -> None:
        async with BrowserHost() as host:
            for site in SITE_IDS:
                rec = synthetic_recording(site, "v1", routine_id=routine_id, base_urls=dry_urls,
                                          recording_id=f"rec_demo{site}0001")
                bundle, rep = await compile_and_check(rec, model=model, host=host, household=household, base_urls=dry_urls)
                out["reports"][site] = rep.as_dict()
                if bundle is None:
                    raise SystemExit(f"compile failed for site {site}: {'; '.join(rep.errors)}")
                bundle = _retarget(bundle, dry_urls[site], target[site])
                path = routine_dir(routine_id, root) / FILES[site]
                same = path.exists() and _digest(json.loads(path.read_text())) == _digest(bundle)
                if same:
                    out["actions"][site] = "unchanged"
                else:
                    save_bundle(bundle, name=None if site == "a" else site, root=root)
                    out["actions"][site] = "written"
                out["paths"].append(path)
                log(f"  site {site}: {out['actions'][site]:9s} {path}  (dry run ok, {rep.dry_run['steps_run']} steps, "
                    f"{len(bundle['steps'])} in the bundle, limited_capability from household: "
                    f"{bool(rep.inserted_from_household)})")

    with SandboxCluster(ephemeral=True) as private:
        log("dry run on private sandbox sites (ephemeral ports); the shared sites are not touched")
        run_async(go(private.urls))
    return out


def install(routine_id: str = ROUTINE_ID, data_dir: Path | None = None, *, base_urls: dict[str, str] | None = None) -> list[Path]:
    return install_report(routine_id, data_dir, base_urls=base_urls, log=lambda *_: None)["paths"]


def status(routine_id: str = ROUTINE_ID, data_dir: Path | None = None) -> dict[str, Any]:
    root = Path(data_dir) if data_dir else default_data_dir()
    d = routine_dir(routine_id, root)
    return {"routine": routine_id, "dir": str(d), "bundles": {s: (d / f).exists() for s, f in FILES.items()},
            "consent": (d / "consent.json").exists()}


def main(argv: list[str] | None = None) -> int:
    args = (argv if argv is not None else sys.argv[1:]) or ["status"]
    if args[0] == "install":
        rid = args[1] if len(args) > 1 else ROUTINE_ID
        res = install_report(rid)
        print(f"installed {len(res['paths'])} bundle(s) for {rid}: " + ", ".join(f"{s}={a}" for s, a in res["actions"].items()))
        return 0
    print(json.dumps(status(), indent=1))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
