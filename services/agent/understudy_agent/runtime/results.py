"""Typed results and code-checked completion (BGA-1, BGA-4, BGA-5).

A child's `emit_result` is a CLAIM. `finalise_child` turns it into a `ChildResult` and sets `verified` only when CODE
confirms it: the child really reached an accepted, schema-valid emit, its artifacts exist and look right, and the
role's verifier recomputes the facts from the source data and agrees. A false "done" is recorded as a failed check,
never trusted (the same idea as completion.py for the benefits workflow).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .spec import Artifact, Check, ChildResult, ChildStatus, Spent, StepRecord
from .workspace import Workspace, WorkspaceError, _kind_of, _ref

OUTPUT_SCHEMAS: dict[str, dict[str, Any]] = {}


def register_schema(schema_id: str, schema: dict[str, Any]) -> None:
    OUTPUT_SCHEMAS[schema_id] = schema


def output_schemas() -> dict[str, dict[str, Any]]:
    from . import exemplars  # noqa: F401  (registers the exemplar schemas)

    return OUTPUT_SCHEMAS


@dataclass
class VerifyCtx:
    """Everything a verifier may look at. `params` is trusted (it came from the API caller, not from the model)."""
    role: str
    output: dict[str, Any]
    ws: Workspace | None
    params: dict[str, Any]
    artifacts: list[Artifact] = field(default_factory=list)
    repo_copy: Path | None = None


Verifier = Callable[[VerifyCtx], list[Check]]
VERIFIERS: dict[str, Verifier] = {}


def register_verifier(role: str, fn: Verifier) -> None:
    VERIFIERS[role] = fn


def close(a: float, b: float, rel: float = 1e-6, abs_: float = 1e-6) -> bool:
    return abs(a - b) <= max(abs_, rel * max(abs(a), abs(b)))


PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def png_ok(path: Path, min_bytes: int = 1500, min_side: int = 100) -> bool:
    try:
        data = path.read_bytes()
        if not data.startswith(PNG_MAGIC) or len(data) < min_bytes:
            return False
        from PIL import Image  # pillow is an agent dependency

        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            return im.width >= min_side and im.height >= min_side
    except Exception:  # noqa: BLE001
        return False


def finalise_child(*, spec_id: str, role: str, status: ChildStatus, reason: str, claimed: bool, output: dict[str, Any] | None,
                   steps: list[StepRecord], spent: Spent, ws: Workspace | None, params: dict[str, Any],
                   run_dir: Path | None, repo: Path | None = None, collect: bool = True,
                   recoveries: int = 0) -> ChildResult:
    """Build the typed result. Artifacts are collected by code from WORK/out (and the patch from the worktree diff);
    `verified` needs status done, an accepted emit and every check ok."""
    checks: list[Check] = []
    artifacts: list[Artifact] = []
    out = dict(output or {})
    if ws is not None and ws.work is not None and run_dir is not None and collect:
        dest = run_dir / "artifacts" / spec_id
        try:
            artifacts = ws.collect_artifacts(dest, repo)
            if ws.kind == "worktree":
                patch = ws.diff_patch()
                if patch.strip():
                    dest.mkdir(parents=True, exist_ok=True)
                    pp = dest / f"{role}.patch"
                    pp.write_text(patch)
                    artifacts.append(Artifact(name=pp.name, kind="patch", path_ref=_ref(pp, repo),
                                              sha256=hashlib.sha256(patch.encode()).hexdigest(), bytes=len(patch.encode())))
        except WorkspaceError as e:
            checks.append(Check(name="artifacts_collected", ok=False, detail=e.code))
    checks.append(Check(name="emitted_valid_result", ok=bool(claimed and output is not None), detail="" if claimed else "no_emit"))
    if claimed and status == "done":
        verifier = VERIFIERS.get(role)
        if verifier is None:
            checks.append(Check(name="verifier_registered", ok=False, detail="none"))
        else:
            try:
                checks.extend(verifier(VerifyCtx(role=role, output=out, ws=ws, params=params, artifacts=artifacts,
                                                  repo_copy=ws.repo_copy if ws else None)))
            except Exception as e:  # noqa: BLE001 - a verifier that cannot run is a failed check, not a pass
                checks.append(Check(name="verifier_ran", ok=False, detail=type(e).__name__))
    verified = status == "done" and bool(claimed) and all(c.ok for c in checks)
    final_status: ChildStatus = status
    if status == "done" and not verified:
        final_status = "failed"
        reason = reason or "claimed done but a check failed"
    elif status == "failed" and not claimed and reason == "":
        final_status = "no_result"
    return ChildResult(child_id=spec_id, role=role, status=final_status, verified=verified, claimed_success=claimed,
                       output=out, checks=checks, artifacts=artifacts,
                       steps=steps, spent=spent, recoveries=recoveries, reason=re.sub(r"[^A-Za-z0-9_:.,\- ]", "", reason)[:160])
