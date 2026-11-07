"""The typed tools a child can use (BGA-1). Six, fixed:

    read_file(path, offset?, max_bytes?)         text from inside the workspace            (untrusted text)
    list_dir(path?)                              names and sizes inside the workspace      (untrusted text)
    git_log(max_commits?, save_as?)              read-only aggregates of the worktree's history (numbers only)
    run_python(path)                             a script in the workspace, sandboxed: no network, no writes outside
    write_workspace(path, content)               a text file inside the workspace
    emit_result(result_file)                     the child's typed result, read and schema-checked by CODE

Every call is first turned into ONE typed pipeline action and authorised by `SafetyPipeline.authorise` (see
`pipeline_action`): reads map to the browser-neutral `extract` kind, writes and code runs to `fill`; the real arguments
are validated here, the workspace refuses traversal, symlinks and credential-looking names, and nothing can write
outside WORK. There is no spawn tool: a child cannot start another agent (depth 1).

What a tool returns to the planner is either numbers and short enum codes (`trusted`, passed through
`assert_trusted_fields`), or text from a file (`text`), which goes through the injection detector and the quarantined
reader before the planner sees any of it.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import jsonschema

from ..security.gates import TargetInfo
from ..security.labels import sensitive_path
from . import policy
from .gitstats import parse_git_log, summarize
from clicky_lift import Condition, equals
from .sandbox import PyResult, run_python
from .spec import AgentSpec, TOOL_NAMES
from .workspace import Workspace, WorkspaceError

_TOKEN = re.compile(r"^[a-z0-9_.:\-]{1,40}$")


class StepRejected(ValueError):
    """The proposed step is not a valid typed tool call. `code` is a short stable reason."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class ToolCtx:
    ws: Workspace
    spec: AgentSpec
    output_schema: dict[str, Any]
    is_cancelled: Callable[[], bool] = lambda: False
    remaining: Callable[[], float] = lambda: policy.PY_TIMEOUT_S      # seconds of the child's time budget left
    emitted: dict[str, Any] | None = None


@dataclass
class ToolOutcome:
    ok: bool
    codes: list[str] = field(default_factory=list)
    trusted: dict[str, Any] = field(default_factory=dict)      # numbers, booleans, short enum tokens only
    text: str | None = None                                    # untrusted text for the detector and the reader
    fields: dict[str, Any] = field(default_factory=dict)       # scalars READ BY CODE after the step, for the postcheck
    blockers: set[str] = field(default_factory=set)            # tokens such as timed_out; they beat any success
    signals: dict[str, int | float] = field(default_factory=dict)   # typed numbers a vetted script reported (status file)
    terminal: bool = False
    py: PyResult | None = None


def assert_trusted_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Only numbers, booleans and short lower-case tokens may go to the planner without the reader."""
    for k, v in fields.items():
        if not _TOKEN.match(str(k)):
            raise ValueError("untrusted key")
        if isinstance(v, bool) or v is None or isinstance(v, (int, float)):
            continue
        if isinstance(v, str) and _TOKEN.match(v):
            continue
        raise ValueError(f"field {k!r} is not a plain number or token")
    return fields


# ------------------------------------------------------------------------------------------------ argument shapes
@dataclass(frozen=True)
class ToolDef:
    name: str
    args: frozenset[str]
    required: frozenset[str]
    about: str


TOOLS: dict[str, ToolDef] = {
    "read_file": ToolDef("read_file", frozenset({"path", "offset", "max_bytes"}), frozenset({"path"}),
                         "read a text file inside the workspace (up to 20000 bytes per call)"),
    "list_dir": ToolDef("list_dir", frozenset({"path"}), frozenset(), "list a directory inside the workspace ('.' for the root)"),
    "git_log": ToolDef("git_log", frozenset({"max_commits", "save_as"}), frozenset(),
                       "read the repository history; saves structured data to save_as (default gitlog.json) and returns numbers"),
    "run_python": ToolDef("run_python", frozenset({"path"}), frozenset({"path"}),
                          "run a .py file from the workspace in a sandbox: no network, no writes outside the workspace, 30 s; "
                          "stdout and stderr are saved to .run/stdout.txt and .run/stderr.txt"),
    "write_workspace": ToolDef("write_workspace", frozenset({"path", "content"}), frozenset({"path", "content"}),
                               "write a UTF-8 text file inside the workspace"),
    "emit_result": ToolDef("emit_result", frozenset({"result_file"}), frozenset({"result_file"}),
                           "finish: name a JSON file in the workspace holding your result; code checks it against the schema"),
}
assert tuple(TOOLS) == TOOL_NAMES, "spec.TOOL_NAMES and tools.TOOLS must list the same tools"

_INT_ARGS = {"offset": (0, 10_000_000), "max_bytes": (1, policy.MAX_READ_BYTES), "max_commits": (1, 1000)}
_STR_ARGS = {"path": 200, "save_as": 120, "result_file": 200, "content": policy.MAX_FILE_BYTES}


def normalise_step(raw: Any, allowed_tools: list[str]) -> tuple[str, dict[str, Any]]:
    """Check the model's one-step proposal. Returns (tool, args) or raises StepRejected. Unknown or extra keys are
    refused, so a hijacked reply such as {"kind": "goto", ...} can never be mistaken for a tool call."""
    if not isinstance(raw, dict):
        raise StepRejected("not_an_object")
    tool = raw.get("tool")
    if not isinstance(tool, str) or tool not in TOOLS:
        raise StepRejected("unknown_tool")
    if tool not in allowed_tools:
        raise StepRejected("tool_not_in_spec")
    args = {k: v for k, v in raw.items() if k not in ("tool", "reason") and v is not None}
    td = TOOLS[tool]
    if set(args) - td.args:
        raise StepRejected("unexpected_arg")
    if td.required - set(args):
        raise StepRejected("missing_arg")
    for k, v in args.items():
        if k in _INT_ARGS:
            lo, hi = _INT_ARGS[k]
            if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
                raise StepRejected("bad_arg_value")
        elif k in _STR_ARGS:
            if not isinstance(v, str) or len(v) > _STR_ARGS[k] or (k != "content" and not v):
                raise StepRejected("bad_arg_value")
    return tool, args


def pipeline_action(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    """The ONE typed action the SafetyPipeline sees for a tool call (layers 3 to 8 all run on it).

    reads and the final emit -> `extract` {name: <tool>, selector: <path>}   (class: read; never gated)
    writes and code runs     -> `fill`    {selector: <path>, value: "sha256:<12>"}   (class: fill; credential-looking
                                          paths or content become class `credential`: always a human click)
    The content itself is never put in an action (it would be audited and hashed); a digest stands in for it.
    """
    sel = str(args.get("path") or args.get("result_file") or args.get("save_as") or ".")[:280]
    if tool in ("write_workspace", "run_python"):
        body = args.get("content", "") if tool == "write_workspace" else sel
        if sensitive_path(sel):
            value = sel                       # layer 4 classifies credential-looking paths: always a human click
        elif sensitive_path(args.get("content")):
            value = ".ssh/content"            # the same class, when the CONTENT points at credential material
        else:
            value = "sha256:" + hashlib.sha256(str(body).encode()).hexdigest()[:12]
        return {"kind": "fill", "args": {"selector": sel, "value": value}}
    return {"kind": "extract", "args": {"name": tool, "selector": sel}}


def pipeline_target(tool: str, args: dict[str, Any], ws: Workspace | None) -> TargetInfo:
    """The TARGET the pipeline sees for the action `pipeline_action` builds (S-28: a fill whose target trusted code could not read is
    a human's call). A write or a code run addresses ONE FILE in the child's own workspace, and TRUSTED code reads that here: the
    path is resolved by `Workspace.resolve` (inside the workspace, no symlink, no escape). A path that does not resolve is an
    UNREADABLE target, so the gate sends it to a human. Reads and the final emit are `extract` steps that type nothing (class read)."""
    if tool not in ("write_workspace", "run_python"):
        return TargetInfo()
    if ws is None:
        return TargetInfo()
    sel = str(args.get("path") or args.get("result_file") or args.get("save_as") or ".")[:280]
    try:
        ws.resolve(sel)
    except (WorkspaceError, ValueError, OSError):
        return TargetInfo()
    return TargetInfo(label="", role="workspace_file")


# ------------------------------------------------------------------------------------------------ postconditions
# One declared condition per tool. The fields are read by CODE after the step (never a model's claim); a field that was
# not produced is "uncertain", a false one is "failed", and a blocker token beats any success.
POSTCONDITIONS: dict[str, Condition] = {
    "read_file": Condition.of(equals("readable", True), equals("bytes_within_total", True)),
    "list_dir": Condition.of(equals("listed", True)),
    "git_log": Condition.of(equals("commits_found", True), equals("saved_parses", True)),
    "run_python": Condition.of(equals("exit_zero", True)),
    "write_workspace": Condition.of(equals("file_exists", True), equals("size_matches", True), equals("content_matches", True)),
    "emit_result": Condition.of(equals("schema_valid", True)),
}


def _refused(e: WorkspaceError, **fields: Any) -> ToolOutcome:
    return ToolOutcome(False, [f"refused:{e.code}"], {"ok": False, "refused": True}, fields=fields)


# ------------------------------------------------------------------------------------------------ implementations
def _read_file(ctx: ToolCtx, a: dict[str, Any]) -> ToolOutcome:
    try:
        text, total, truncated = ctx.ws.read_text(a["path"], a.get("offset", 0), a.get("max_bytes", policy.MAX_READ_BYTES))
    except WorkspaceError as e:
        return _refused(e, readable=False)
    n = len(text.encode("utf-8", "replace"))
    return ToolOutcome(True, ["read"], {"ok": True, "bytes": n, "total_bytes": total, "truncated": truncated}, text=text,
                       fields={"readable": True, "bytes_within_total": n <= total + 3})


def _list_dir(ctx: ToolCtx, a: dict[str, Any]) -> ToolOutcome:
    try:
        entries = ctx.ws.list_dir(a.get("path", "."))
    except WorkspaceError as e:
        return _refused(e, listed=False)
    text = "\n".join(f"{e['kind']} {e['bytes']} {e['name']}" for e in entries)
    return ToolOutcome(True, ["listed"], {"ok": True, "entries": len(entries)}, text=text or "(empty)", fields={"listed": True})


def _git_log(ctx: ToolCtx, a: dict[str, Any]) -> ToolOutcome:
    save_as = a.get("save_as", "gitlog.json")
    try:
        if ctx.ws.kind != "worktree":
            raise WorkspaceError("not_a_worktree")
        log = parse_git_log(ctx.ws.work, max_commits=a.get("max_commits", 300))  # type: ignore[arg-type]
        ctx.ws.write_text(save_as, json.dumps(log, separators=(",", ":")))
    except WorkspaceError as e:
        return _refused(e, commits_found=False, saved_parses=False)
    s = summarize(log)
    try:
        parses = json.loads(ctx.ws.resolve(save_as).read_text()) is not None
    except (OSError, ValueError, WorkspaceError):
        parses = False
    return ToolOutcome(True, ["git_log"], {"ok": True, **s, "saved": True},
                       fields={"commits_found": s["n_commits"] > 0, "saved_parses": parses})


def read_signals(ws: Workspace) -> dict[str, int | float]:
    """Typed signals from the status file a vetted script writes: only registered names, only finite numbers (booleans become
    0 or 1). Anything else is dropped. The file is removed before each run, so a crashed script leaves no stale signals."""
    try:
        p = ws.resolve(policy.STATUS_FILE)
        if not p.is_file() or p.stat().st_size > 4096:
            return {}
        raw = json.loads(p.read_text()).get("signals", {})
    except (WorkspaceError, OSError, ValueError, AttributeError):
        return {}
    out: dict[str, int | float] = {}
    for k, v in (raw.items() if isinstance(raw, dict) else []):
        if k in policy.SIGNAL_NAMES and isinstance(v, (int, float)) and math.isfinite(v) and abs(v) < 1_000_000:
            out[k] = int(v) if isinstance(v, (bool, int)) else round(float(v), 2)
    return out


def _run_python(ctx: ToolCtx, a: dict[str, Any]) -> ToolOutcome:
    try:
        try:
            ctx.ws.resolve(policy.STATUS_FILE).unlink(missing_ok=True)
        except (WorkspaceError, OSError):
            pass
        res = run_python(ctx.ws, a["path"], is_cancelled=ctx.is_cancelled,
                         timeout_s=max(1.0, min(policy.PY_TIMEOUT_S, ctx.remaining())))
    except WorkspaceError as e:
        return _refused(e, exit_zero=False)
    integ = res.integrity or {}
    out_dir = ctx.ws.work / "out" if ctx.ws.work else None
    out_n = len(list(out_dir.iterdir())) if out_dir is not None and out_dir.is_dir() else 0
    trusted = {"ok": res.ok, "exit_code": -1 if res.exit_code is None else res.exit_code, "timed_out": res.timed_out,
               "seconds": res.duration_s, "stdout_bytes": res.stdout_bytes, "stderr_bytes": res.stderr_bytes,
               "out_files": out_n, "killed": res.killed_reason or "none"}
    blockers = set()
    if res.timed_out:
        blockers.add("timed_out")
    if res.killed_reason:
        blockers.add("killed_" + res.killed_reason)
    if integ.get("symlinks") or integ.get("hardlinks") or integ.get("special"):
        blockers.add("sandbox_escape_attempt")
    if integ.get("over_limit"):
        blockers.add("workspace_over_limit")
    return ToolOutcome(res.ok, ["ran" if res.ok else f"run_failed:{res.killed_reason or res.exit_code}"], trusted, py=res,
                       fields={"exit_zero": res.exit_code == 0}, blockers=blockers, signals=read_signals(ctx.ws))


def _write_workspace(ctx: ToolCtx, a: dict[str, Any]) -> ToolOutcome:
    content: str = a["content"]
    if sensitive_path(content):
        return ToolOutcome(False, ["refused:credential_reference"], {"ok": False, "refused": True},
                           fields={"file_exists": False}, blockers={"credential_reference"})
    try:
        n, sha = ctx.ws.write_text(a["path"], content)
        p = ctx.ws.resolve(a["path"])
        on_disk = p.read_bytes()
    except (WorkspaceError, OSError) as e:
        return _refused(e if isinstance(e, WorkspaceError) else WorkspaceError("io_error"), file_exists=False)
    return ToolOutcome(True, ["wrote"], {"ok": True, "bytes": n},
                       fields={"file_exists": p.is_file(), "size_matches": len(on_disk) == n,
                               "content_matches": hashlib.sha256(on_disk).hexdigest() == sha})


def _emit_result(ctx: ToolCtx, a: dict[str, Any]) -> ToolOutcome:
    try:
        text, total, truncated = ctx.ws.read_text(a["result_file"], 0, 100_000)
    except WorkspaceError as e:
        return _refused(e, schema_valid=False)
    try:
        obj = json.loads(text)
        jsonschema.validate(obj, ctx.output_schema)
        if not isinstance(obj, dict) or truncated:
            raise ValueError("shape")
    except (ValueError, jsonschema.ValidationError):
        return ToolOutcome(False, ["schema_violation"], {"ok": False, "schema_valid": False}, fields={"schema_valid": False})
    ctx.emitted = obj
    return ToolOutcome(True, ["emitted"], {"ok": True, "schema_valid": True}, terminal=True, fields={"schema_valid": True})


_IMPL: dict[str, Callable[[ToolCtx, dict[str, Any]], ToolOutcome]] = {
    "read_file": _read_file, "list_dir": _list_dir, "git_log": _git_log, "run_python": _run_python,
    "write_workspace": _write_workspace, "emit_result": _emit_result,
}


def run_tool(tool: str, args: dict[str, Any], ctx: ToolCtx) -> ToolOutcome:
    return _IMPL[tool](ctx, args)


def tool_help(allowed: list[str]) -> str:
    """Trusted text describing the child's tools for its planner prompt."""
    return "\n".join(f"- {t}({', '.join(sorted(TOOLS[t].args))}): {TOOLS[t].about}" for t in allowed)


# ------------------------------------------------------------------------------------------------ the step schema
def child_step_schema(child_id: str, allowed: list[str]) -> dict[str, Any]:
    """A flat object: every field optional except `tool` and `reason`, so it fits strict structured outputs. The title
    carries the child id so mock scripts can be queued per child."""
    return {
        "title": f"child_step_{child_id}",
        "type": "object",
        "required": ["tool", "reason"],
        "properties": {
            "tool": {"type": "string", "enum": list(allowed)},
            "reason": {"type": "string", "maxLength": 200},
            "path": {"type": "string", "maxLength": 200},
            "content": {"type": "string", "maxLength": policy.MAX_FILE_BYTES},
            "offset": {"type": "integer", "minimum": 0},
            "max_bytes": {"type": "integer", "minimum": 1, "maximum": policy.MAX_READ_BYTES},
            "max_commits": {"type": "integer", "minimum": 1, "maximum": 1000},
            "save_as": {"type": "string", "maxLength": 120},
            "result_file": {"type": "string", "maxLength": 200},
        },
    }


# ------------------------------------------------------------------------------------------------ menu mode
def resolve_menu_step(menu: Any, raw: Any, allowed_tools: list[str]) -> tuple[str, dict[str, Any]]:
    """Turn the model's reply of ids ({tool, file, template}) into a concrete tool call, or raise StepRejected.

    The model never names a path or supplies text: `file` selects a path from the role's menu and `template` selects a
    vetted script. So nothing about the worker's files has to go to the model, and nothing it says can name a path
    outside the menu. Unknown ids, extra keys and ids that do not fit the tool are refused."""
    if not isinstance(raw, dict):
        raise StepRejected("not_an_object")
    extra = set(raw) - {"tool", "file", "template", "reason"}
    if extra:
        raise StepRejected("unexpected_arg")
    tool = raw.get("tool")
    if not isinstance(tool, str) or tool not in TOOLS:
        raise StepRejected("unknown_tool")
    if tool not in allowed_tools:
        raise StepRejected("tool_not_in_spec")
    file_id, tpl = raw.get("file"), raw.get("template")
    file_id = None if file_id in (None, "none") else file_id
    tpl = None if tpl in (None, "none") else tpl
    if file_id is not None and (not isinstance(file_id, str) or file_id not in menu.files):
        raise StepRejected("unknown_file_id")
    if tpl is not None and (not isinstance(tpl, str) or tpl not in menu.templates):
        raise StepRejected("unknown_template_id")
    if tool == "write_workspace":
        if file_id is None or tpl is None:
            raise StepRejected("missing_arg")
        return tool, {"path": menu.files[file_id], "content": menu.templates[tpl]}
    if tpl is not None:
        raise StepRejected("unexpected_arg")
    if tool == "list_dir":
        return tool, {"path": "."}
    if tool == "git_log":
        return tool, {"max_commits": menu.max_commits, "save_as": menu.files.get(file_id or "gitlog", "gitlog.json")}
    if file_id is None:
        raise StepRejected("missing_arg")
    if tool == "emit_result":
        return tool, {"result_file": menu.files[file_id]}
    return tool, {"path": menu.files[file_id]}                       # read_file, run_python


def menu_step_schema(role: str, tools: list[str], files: list[str], templates: list[str]) -> dict[str, Any]:
    """The reply shape in menu mode: ids only, no free text, so the exchange can pass the egress guard."""
    return {
        "title": f"child_step_{role}",
        "type": "object",
        "required": ["tool", "file", "template"],
        "properties": {
            "tool": {"type": "string", "enum": sorted(tools)},
            "file": {"type": "string", "enum": [*files, "none"]},
            "template": {"type": "string", "enum": [*templates, "none"]},
        },
    }
