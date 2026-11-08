"""Claude CLI background agents: a monitored child process (docs/TASKS.md).

Knack's task planner starts the owner's own `claude` command as a child, `claude -p "<prompt>" --output-format stream-json
--verbose`, in its own process group, in a working folder, and watches it:

* the child's environment is an ALLOW-LIST (`HOME PATH LANG TERM USER TMPDIR`, nothing else): Knack's own model keys and every other
  variable are never passed, and nothing here reads, copies or prints a Claude credential (the child finds the owner's own login
  through HOME, as it does in a terminal);
* the stream-json events become short progress lines (a tool name and a file's base name, never contents, commands or prompts);
* a wall-clock cap (default 30 minutes), an idle cap, an output-size cap, the global kill file, and `stop()` all end it: SIGTERM to the
  whole process group, then SIGKILL after a short grace, then a last SIGKILL sweep so no grandchild outlives the task;
* a crash, a flood or a non-zero exit becomes ONE plain reason (stderr is classified, never shown);
* the final message is returned as untrusted text: the caller keeps the full text in a file and uses one line of it as the result.

Permission scope: `files_and_commands` = `--permission-mode acceptEdits` plus `--allowedTools Read,Edit,Write,Glob,Grep,Bash` and
`--permission-prompts none` (anything else that would prompt is denied, so the child can never hang on a prompt). `everything` =
`--dangerously-skip-permissions`, used only when the worker picked that second option on the consent card for this task. Deny rules
for Knack's own protected files are added through `--settings` as defence in depth; they are NOT a sandbox (the owner chose full
computer access, and a shell command can reach anything the account can).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

ALLOWED_ENV = ("HOME", "PATH", "LANG", "TERM", "USER", "TMPDIR")
SAFE_PATH_TAIL = ("/usr/local/bin", "/opt/homebrew/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin")
DEFAULT_TOOLS = ("Read", "Edit", "Write", "Glob", "Grep", "Bash")
DEFAULT_MAX_SECONDS = 30 * 60
DEFAULT_IDLE_SECONDS = 10 * 60
DEFAULT_MAX_OUT_BYTES = 20 * 1024 * 1024
LINE_MAX = 1 << 20
TERM_GRACE_S = 3.0
QUIET_AFTER_S = 30.0
BUDGET_GRACE_S = 0.5            # a reported cost at the limit must persist this long without a result before Knack ends the child itself


# ----------------------------------------------------------------------------------------------------- locating and env
def claude_binary(env: dict[str, str] | None = None, home: Path | None = None) -> str | None:
    """`KNACK_CLAUDE_BIN` (tests point it at a fake), else `~/.local/bin/claude`, else `claude` on PATH. None if not found."""
    e = os.environ if env is None else env
    forced = (e.get("KNACK_CLAUDE_BIN") or "").strip()
    if forced:
        return forced
    cand = (home or Path.home()) / ".local" / "bin" / "claude"
    if cand.is_file() and os.access(cand, os.X_OK):
        return str(cand)
    return shutil.which("claude", path=e.get("PATH"))


def child_env(parent: dict[str, str] | None = None) -> dict[str, str]:
    """The only environment the child gets. PATH always ends with the standard system directories (an app started from the
    dock has a bare PATH, and the agent's shell commands need `git`, `python3` and friends)."""
    p = os.environ if parent is None else parent
    out = {k: p[k] for k in ALLOWED_ENV if k in p and p[k] != ""}
    venv = (p.get("VIRTUAL_ENV") or "").rstrip("/")
    # Knack's own virtualenv is not the person's Python: its bin directory is dropped (VIRTUAL_ENV itself is not passed either)
    parts = [x for x in out.get("PATH", "").split(":") if x and not (venv and x.rstrip("/") == venv + "/bin")
             and not x.rstrip("/").endswith("/.venv/bin")]
    for d in SAFE_PATH_TAIL:
        if d not in parts:
            parts.append(d)
    out["PATH"] = ":".join(parts)
    return out


def protected_deny_rules(data: Path, repo: Path | None = None, state_dirs: list[Path] | None = None) -> list[str]:
    """Deny rules (Claude Code permission syntax; `//` marks an absolute path) for the files that hold Knack's safety state. `state_dirs`
    are the folders that hold the worker's memory and other private state (`~/.understudy`, or `UNDERSTUDY_HOME`): neither read nor changed."""
    def a(p: Path) -> str:
        return "//" + str(p).lstrip("/")

    rules: list[str] = []
    for d in state_dirs or []:
        rules.append(f"Edit({a(d)}/**)")
        rules.append(f"Read({a(d)}/**)")
    for name in ("KILL", "denylist.json", "audit.jsonl", "owner_tokens.json", "rung_cleared.json", ".token", ".queue_key",
                 "task_settings.json"):
        rules.append(f"Edit({a(data / name)})")
    for name in ("queue", "routines", "tasks"):
        rules.append(f"Edit({a(data / name)}/**)")
    for name in (".token", ".queue_key", "owner_tokens.json"):
        rules.append(f"Read({a(data / name)})")
    if repo is not None:
        rules.append(f"Read({a(repo / '.env')})")
        rules.append(f"Edit({a(repo / '.env')})")
    return rules


# ------------------------------------------------------------------------------------------------------ argv and prompt
def build_prompt(text: str, cwd: str, skill_names: list[str] | None = None) -> str:
    names = [re.sub(r"[^A-Za-z0-9 ._:\-]", "", n)[:60] for n in (skill_names or [])][:4]
    hint = f"\nSkills that may help (from the user's own setup): {', '.join(names)}." if names else ""
    return (
        "Task from a Knack user, working on their Mac. Work in the folder " + cwd + ". Do the task below. "
        "Do not ask questions: if something is unclear, choose sensibly and say what you chose. If the task mentions a file or folder "
        "without a path (for example 'this CSV'), look in the Desktop, Documents and Downloads folders for the most recently changed "
        "match and say which one you used. "
        "When you are done, finish with ONE short paragraph that says what you did and where the files are."
        + hint + "\n\nTask:\n" + text.strip()
    )


def build_argv(binary: str, prompt: str, *, scope: str, session_id: str, add_dirs: list[str] | None = None,
               deny_rules: list[str] | None = None, max_turns: int | None = None, skills_enabled: bool = True,
               skills_off: list[str] | None = None, max_budget_usd: float | None = None) -> list[str]:
    argv = [binary, "-p", prompt, "--output-format", "stream-json", "--verbose", "--permission-prompts", "none",
            "--session-id", session_id]
    if max_turns:
        argv += ["--max-turns", str(int(max_turns))]
    if max_budget_usd:                          # the spend brake: the CLI stops itself at this amount (Knack also watches the cost it reports)
        argv += ["--max-budget-usd", f"{float(max_budget_usd):.2f}"]
    if not skills_enabled:                      # Settings: "Use my Claude Code skills" is off, so the child loads none
        argv += ["--disable-slash-commands"]
    elif skills_off:                            # individual skills the worker switched off (best effort: a permission rule on the Skill tool)
        argv += ["--disallowedTools", ",".join(f"Skill({re.sub(r'[^A-Za-z0-9 ._:-]', '', n)[:60]})" for n in skills_off[:50])]
    if deny_rules:
        argv += ["--settings", json.dumps({"permissions": {"deny": list(deny_rules)}}, separators=(",", ":"))]
    if scope == "everything":
        argv += ["--dangerously-skip-permissions"]
    elif scope == "files_and_commands":
        argv += ["--permission-mode", "acceptEdits", "--allowedTools", ",".join(DEFAULT_TOOLS)]
    else:
        raise ValueError("scope must be files_and_commands or everything")
    for d in add_dirs or []:
        argv += ["--add-dir", d]
    return argv


def command_hash(argv: list[str], cwd: str) -> str:
    """What the worker pinned on the card: a hash over the exact command line, the folder and the allowed environment keys."""
    h = hashlib.sha256()
    for part in [*argv, "\0cwd", cwd, "\0env", ",".join(ALLOWED_ENV)]:
        h.update(part.encode("utf-8", "replace"))
        h.update(b"\0")
    return h.hexdigest()


# --------------------------------------------------------------------------------------------------------- progress
def _base(path: Any) -> str:
    name = os.path.basename(str(path or "").rstrip("/"))
    name = re.sub(r"[^A-Za-z0-9 ._()+\-]", "?", name)[:40].strip()
    return name or "a file"


_TOOL_LINES: dict[str, Callable[[dict[str, Any]], str]] = {
    "Read": lambda i: f"Reading {_base(i.get('file_path') or i.get('path'))}",
    "Edit": lambda i: f"Editing {_base(i.get('file_path'))}",
    "MultiEdit": lambda i: f"Editing {_base(i.get('file_path'))}",
    "Write": lambda i: f"Writing {_base(i.get('file_path'))}",
    "NotebookEdit": lambda i: f"Editing {_base(i.get('notebook_path'))}",
    "Glob": lambda i: "Looking for files",
    "Grep": lambda i: "Searching the files",
    "LS": lambda i: "Listing a folder",
    "Bash": lambda i: "Running a command",
    "BashOutput": lambda i: "Checking on a command",
    "WebFetch": lambda i: "Reading a web page",
    "WebSearch": lambda i: "Searching the web",
    "Task": lambda i: "Starting a helper",
    "Agent": lambda i: "Starting a helper",
    "TodoWrite": lambda i: "Updating its plan",
    "Skill": lambda i: "Using a skill",
}


def tool_line(name: str, tool_input: Any) -> str:
    inp = tool_input if isinstance(tool_input, dict) else {}
    fn = _TOOL_LINES.get(name)
    if fn is not None:
        try:
            return fn(inp)
        except Exception:  # noqa: BLE001
            return "Working"
    if name.startswith("mcp__"):
        return "Using a connected tool"
    safe = re.sub(r"[^A-Za-z0-9_.\-]", "", name)[:30]
    return f"Using {safe}" if safe else "Working"


@dataclass
class StreamState:
    result_text: str | None = None
    is_error: bool = False
    subtype: str = ""
    session_id: str | None = None
    written: list[str] = field(default_factory=list)
    turns: int = 0
    refused: int = 0                   # tool calls the permission settings refused (the deny rules for Knack's protected files)
    cost_usd: float | None = None      # `total_cost_usd` from the result event, as the CLI reports it (a number, kept in the ledger row)


def parse_line(raw: bytes, st: StreamState) -> list[str]:
    """One stream-json line -> zero or more progress lines; the final `result` event is stored in `st`. Never raises."""
    try:
        obj = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return []
    if not isinstance(obj, dict):
        return []
    t = obj.get("type")
    out: list[str] = []
    c = obj.get("total_cost_usd")                # the running cost, wherever the CLI reports it (always on the result event)
    if isinstance(c, (int, float)) and not isinstance(c, bool) and 0 <= c < 1e6:
        st.cost_usd = max(float(c), st.cost_usd or 0.0)
    if t == "system" and obj.get("subtype") == "init":
        sid = obj.get("session_id")
        st.session_id = str(sid)[:64] if isinstance(sid, str) else st.session_id
        out.append("Started")
    elif t == "assistant":
        msg = obj.get("message")
        content = msg.get("content") if isinstance(msg, dict) else None
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    name = str(block.get("name") or "")
                    inp = block.get("input")
                    out.append(tool_line(name, inp))
                    if name in ("Write", "Edit", "MultiEdit") and isinstance(inp, dict) and isinstance(inp.get("file_path"), str):
                        if len(st.written) < 50:
                            st.written.append(inp["file_path"])
            st.turns += 1
    elif t == "user":
        # A tool call the permission settings refused (seen in the second real run: "File is in a directory that is denied by your
        # permission settings."). One plain line, no file name and no text from the result.
        msg = obj.get("message")
        content = msg.get("content") if isinstance(msg, dict) else None
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result" and block.get("is_error"):
                    body = block.get("content")
                    text = body if isinstance(body, str) else " ".join(x.get("text", "") for x in body if isinstance(x, dict)) \
                        if isinstance(body, list) else ""
                    if "denied by your permission" in text:
                        st.refused += 1
                        out.append("A step was refused by the protected-files rules")
    elif t == "result":
        r = obj.get("result")
        st.result_text = r if isinstance(r, str) else ""
        st.is_error = bool(obj.get("is_error"))
        st.subtype = str(obj.get("subtype") or "")[:40]
    return out


# ------------------------------------------------------------------------------------------------------------- reasons
_AUTH = re.compile(r"(not logged in|please run /login|log ?in|invalid api key|authentication|unauthori[sz]ed|oauth|credential)", re.I)
_LIMIT = re.compile(r"(usage limit|rate limit|quota|overloaded|credit balance|too many requests)", re.I)

R_AUTH = "Claude isn't signed in on this Mac. Open Terminal, run `claude`, sign in, then try again."
R_LIMIT = "Your Claude account has reached a usage limit. Try again later."
R_NOT_FOUND = "Knack couldn't start Claude on this Mac. Check that the `claude` command is installed."
R_BUDGET = "Reached the spend limit you set."


def classify_failure(stderr_tail: str, result_text: str | None, subtype: str, exit_code: int | None) -> str:
    blob = (stderr_tail or "") + "\n" + (result_text or "")
    if "budget" in (subtype or "").lower():      # the CLI's own stop at --max-budget-usd (its result subtype names the budget)
        return R_BUDGET
    if _AUTH.search(blob):
        return R_AUTH
    if _LIMIT.search(blob):
        return R_LIMIT
    if subtype == "error_max_turns":
        return "The Claude agent ran out of turns before it finished."
    if subtype == "error_during_execution":
        return "The Claude agent hit an error and stopped."
    if exit_code is None:
        return "The Claude agent stopped unexpectedly."
    return f"The Claude agent stopped unexpectedly (exit code {exit_code})."


# --------------------------------------------------------------------------------------------------------------- the run
@dataclass
class ChildOutcome:
    state: str                    # done | failed | stopped
    reason: str | None
    result_text: str
    out_bytes: int
    duration_s: float
    exit_code: int | None
    written: list[str]
    why: str = ""                 # short code: ok | stop | kill | wall | idle | flood | budget | crash | spawn | auth | limit | no_result
    cost_usd: float | None = None


class ClaudeRun:
    """Starts the command, watches it, ends it. `run()` blocks (the manager calls it from the task's own thread); `stop()` may be
    called from any thread."""

    def __init__(self, argv: list[str], cwd: str, env: dict[str, str], *, max_seconds: float = DEFAULT_MAX_SECONDS,
                 idle_seconds: float = DEFAULT_IDLE_SECONDS, max_out_bytes: int = DEFAULT_MAX_OUT_BYTES,
                 on_step: Callable[[str], None] | None = None, on_quiet: Callable[[float], None] | None = None,
                 on_start: Callable[[int], None] | None = None, is_killed: Callable[[], bool] | None = None,
                 popen: Callable[..., Any] = subprocess.Popen, grace_s: float = TERM_GRACE_S, tick_s: float = 0.1,
                 max_budget_usd: float | None = None) -> None:
        self.max_budget_usd = max_budget_usd
        self.argv, self.cwd, self.env = argv, cwd, env
        self.max_seconds, self.idle_seconds, self.max_out_bytes = max_seconds, idle_seconds, max_out_bytes
        self.on_step, self.on_quiet, self.on_start = on_step, on_quiet, on_start
        self.is_killed = is_killed or (lambda: False)
        self._popen, self.grace_s, self.tick_s = popen, grace_s, tick_s
        self._stop = threading.Event()
        self._stop_reason = ""
        self.proc: Any = None
        self.pgid: int | None = None
        self.st = StreamState()
        self.out_bytes = 0
        self._stderr = bytearray()
        self._last = time.monotonic()
        self._flood = False

    # ---- control
    def stop(self, why: str = "stop") -> None:
        self._stop_reason = self._stop_reason or why
        self._stop.set()

    def _signal_group(self, sig: int) -> None:
        if self.pgid is None:
            return
        try:
            os.killpg(self.pgid, sig)
        except (ProcessLookupError, PermissionError):
            pass

    def _over_budget(self) -> bool:
        """The cost the CLI has reported has reached the limit the worker set, and the run has not already delivered its result (a
        finished run is judged by its result, not killed on its way out)."""
        c = self.st.cost_usd
        return bool(self.max_budget_usd and c is not None and c >= self.max_budget_usd and self.st.result_text is None)

    def _terminate(self) -> None:
        """SIGTERM the process group; SIGKILL it after the grace period if the leader is still alive; then sweep the group."""
        self._signal_group(signal.SIGTERM)
        deadline = time.monotonic() + self.grace_s
        while self.proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        self._signal_group(signal.SIGKILL)
        try:
            self.proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            pass

    # ---- readers
    def _read_stdout(self) -> None:
        try:
            for raw in iter(lambda: self.proc.stdout.readline(LINE_MAX), b""):
                self.out_bytes += len(raw)
                self._last = time.monotonic()
                if self.out_bytes > self.max_out_bytes and not self._flood:
                    self._flood = True
                    self._signal_group(signal.SIGKILL)       # at once, not at the next tick: a flood can write hundreds of MB a second
                if self._flood:
                    continue
                if raw.endswith(b"\n"):
                    for line in parse_line(raw, self.st):
                        if self.on_step:
                            self.on_step(line)
        except (ValueError, OSError):
            pass

    def _read_stderr(self) -> None:
        try:
            for raw in iter(lambda: self.proc.stderr.read(4096), b""):
                if len(self._stderr) < 8192:
                    self._stderr += raw[: 8192 - len(self._stderr)]
        except (ValueError, OSError):
            pass

    # ---- the run
    def run(self) -> ChildOutcome:
        t0 = time.monotonic()

        def outcome(state: str, reason: str | None, why: str, code: int | None = None) -> ChildOutcome:
            text = self.st.result_text or ""
            return ChildOutcome(state, reason, text, self.out_bytes, round(time.monotonic() - t0, 2), code, list(self.st.written), why,
                                self.st.cost_usd)

        try:
            Path(self.cwd).mkdir(parents=True, exist_ok=True)
            self.proc = self._popen(self.argv, cwd=self.cwd, env=self.env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, start_new_session=True)
        except (OSError, ValueError):
            return outcome("failed", R_NOT_FOUND, "spawn")
        self.pgid = self.proc.pid                         # start_new_session: the child leads its own process group
        if self.on_start:
            self.on_start(self.proc.pid)
        readers = [threading.Thread(target=self._read_stdout, daemon=True, name="claude-out"),
                   threading.Thread(target=self._read_stderr, daemon=True, name="claude-err")]
        for r in readers:
            r.start()
        forced: tuple[str, str | None, str] | None = None
        quiet_said = 0.0
        over_since: float | None = None               # when the reported cost first reached the limit (it must stay there for a moment)
        try:
            while self.proc.poll() is None:
                if self._over_budget():
                    over_since = over_since if over_since is not None else time.monotonic()
                else:
                    over_since = None
                if self._stop.is_set():
                    forced = ("stopped", "Stopped by you.", "stop") if self._stop_reason != "kill" else \
                        ("stopped", "Stopped by the kill switch.", "kill")
                elif self.is_killed():
                    forced = ("stopped", "Stopped by the kill switch.", "kill")
                elif over_since is not None and time.monotonic() - over_since >= BUDGET_GRACE_S:
                    forced = ("failed", R_BUDGET, "budget")
                elif time.monotonic() - t0 > self.max_seconds:
                    forced = ("failed", f"It ran past the {int(self.max_seconds // 60)} minute limit and was stopped.", "wall")
                elif self._flood:
                    forced = ("failed", "It produced more output than the limit allows and was stopped.", "flood")
                elif time.monotonic() - self._last > self.idle_seconds:
                    forced = ("failed", f"It went quiet for {int(self.idle_seconds // 60)} minutes and was stopped.", "idle")
                if forced is not None:
                    self._terminate()
                    break
                silent = time.monotonic() - self._last
                if self.on_quiet and silent >= QUIET_AFTER_S and silent - quiet_said >= QUIET_AFTER_S:
                    quiet_said = silent
                    self.on_quiet(silent)
                if silent < QUIET_AFTER_S:
                    quiet_said = 0.0
                time.sleep(self.tick_s)
        finally:
            self._signal_group(signal.SIGKILL)            # the sweep: no grandchild (a shell command it started) outlives the task
            try:
                self.proc.wait(timeout=5)
            except Exception:  # noqa: BLE001
                pass
            for r in readers:
                r.join(timeout=2)
            for stream in (self.proc.stdout, self.proc.stderr):
                try:
                    stream.close()
                except Exception:  # noqa: BLE001
                    pass
        code = self.proc.returncode
        if forced is None and self._flood:                    # the reader ended it before the monitor's next tick
            forced = ("failed", "It produced more output than the limit allows and was stopped.", "flood")
        if forced is not None:
            return outcome(forced[0], forced[1], forced[2], code)
        st = self.st
        stderr_tail = self._stderr.decode("utf-8", "replace")
        if st.result_text is not None and not st.is_error and code in (0, None):
            return outcome("done", None, "ok", code)
        why = "crash"
        reason = classify_failure(stderr_tail, st.result_text, st.subtype, code)
        if reason == R_AUTH:
            why = "auth"
        elif reason == R_LIMIT:
            why = "limit"
        elif reason == R_BUDGET:
            why = "budget"
        elif st.result_text is None and code == 0:
            reason, why = "The Claude agent finished without giving a result.", "no_result"
        return outcome("failed", reason, why, code)
