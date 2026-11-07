"""Where the eval reads from, and regeneration of the deterministic synthetic data when it is missing."""
from __future__ import annotations

import sys
from pathlib import Path

from ..store.paths import data_dir, repo_root

PERSONAS = ("nine-to-five", "night-owl", "shift-worker", "irregular")


def resolve_root(root: Path | str | None = None) -> Path:
    return Path(root) if root is not None else data_dir()


def have_apprentices(root: Path | str | None = None) -> bool:
    d = resolve_root(root) / "synthetic" / "apprentices"
    return (d / "events.jsonl").exists() and (d / "truth.json").exists()


def have_personas(root: Path | str | None = None) -> bool:
    base = resolve_root(root) / "synthetic"
    return all((base / p / "events.jsonl").exists() and (base / p / "truth.json").exists() for p in PERSONAS)


def ensure_synthetic(root: Path | str | None = None, log=None) -> list[str]:
    """Run the owners' own seeded generators for whatever is missing (same as ``understudy synth --all``).

    Returns the names regenerated. The generators are deterministic, so this never changes a number that
    already exists; it only fills a fresh checkout.
    """
    log = log or (lambda msg: print(msg, file=sys.stderr))
    root = resolve_root(root)
    done: list[str] = []
    if not have_personas(root):
        from ..personas import write_all_personas

        log(f"eval: personas missing under {root}/synthetic; generating with the seeded generator")
        write_all_personas(root)
        done.append("personas")
    if not have_apprentices(root):
        from ..personas import apprentices

        log(f"eval: apprentices missing under {root}/synthetic; generating with the seeded generator")
        apprentices.generate(root)
        done.append("apprentices")
    return done


def evals_out_dir() -> Path:
    return repo_root() / "evals"
