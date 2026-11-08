"""Static egress guard: no module in the extension layers, the agent service or the agent runtime may reach a model, the network or a
fetcher process except through the reviewed paths. The analysis itself is in ``netscan.py``; this file is the policy.

Three scans (each resolves aliases, constant-folds built strings and follows ``importlib``, ``__import__``, ``getattr``, ``exec``
and ``-c`` code; see ``netscan`` for the full list and its stated limits):

* ``scan_tree()``: the extension layers (``calendar``, ``gitanalysis``, ``proactive``, ``localmodel``, ``plugins``, ``awareness``,
  ``cue``, ``evidence``, ``mlv2``, ``personas_v2`` and their ``routes_*.py``). No model client, ``ModelPort`` or provider class, no
  ``.plan``/``.vision``/``.computer_step`` call, no network, and no process that is a fetcher or carries a URL. ``mlv2`` and
  ``personas_v2`` are pure compute: no process, no URL, no reviewed exception at all.
* ``scan_agent()``: every other module of the agent service (``services/agent/understudy_agent``, except ``models/`` which is the
  provider package, and ``runtime/``). The network rules apply; the model port is the agent's job and is not flagged. A file that
  legitimately uses the network is in ``AGENT_ALLOW`` with a one-line reason, and a client in it must be demonstrably loopback.
* ``scan_runtime()``: the agent runtime. Children run sandboxed with no network, so the network rules apply with no exceptions, and
  any visible direct model call must record a metadata-only ledger line.

A file may use a network client only if it is in ``ALLOW`` (engine) or ``AGENT_ALLOW`` (agent) with a reason, only for what the entry
names, and only if the module carries a literal ``127.0.0.1`` or ``localhost`` (or the one remote host the entry names). Entries marked
``pending`` are not accepted: they are exceptions waiting for a fix and are reported by ``pending_exceptions()`` and in the evaluation.
Nothing is ever allowed to import a model client or ``ModelPort`` in an extension layer.
"""
from __future__ import annotations

import ast
import fnmatch
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .netscan import (
    ALWAYS_CALLS, PORTISH_CALLS, PORTISH_RECEIVER, Allow, Policy, Violation, analyse, dotted, host_of,
)

ENGINE_PKG = Path(__file__).resolve().parents[1]
GUARDED_DIRS = ("calendar", "gitanalysis", "proactive", "localmodel", "plugins", "awareness", "cue", "evidence", "mlv2", "personas_v2", "attention", "hitlist", "insights")
GUARDED_FILES = ("routes_calendar.py", "routes_git.py", "routes_localmodel.py", "routes_proactive.py", "routes_plugins.py",
                 "routes_awareness.py", "routes_cue.py", "routes_evidence.py", "routes_mlv2.py", "routes_personas_v2.py")
#: layers that are pure computation: no model, no network, no process, no URL, and no reviewed exception (``ALLOW`` does not apply)
PURE_COMPUTE_DIRS = ("mlv2", "personas_v2", "attention", "hitlist", "insights")
#: pure-compute packages inside the agent service (no model client, no network, no process, no URL, no reviewed exception)
AGENT_PURE_PREFIXES = ("understudy_agent/context/",)

# Reviewed exceptions for the extension layers. Key = path relative to the engine package, glob allowed. Add an entry only with a
# reason a reviewer accepts; a pure-compute layer can have none.
ALLOW: dict[str, Allow] = {
    "localmodel/client.py": Allow("talks to llama-server on this machine only; assert_loopback() refuses any other host", frozenset({"httpx"}),
                                  loopback_helpers=frozenset({"assert_loopback"})),
    "localmodel/server.py": Allow("starts and probes llama-server on a loopback port (the command is built by _command(); ps reads one process's own command line)",
                                  frozenset({"socket", "httpx", "urllib.request", "http.client"}), loopback_names=frozenset({"config.HOST"}),
                                  processes=frozenset({"ps"}), dynamic_process=True),
    "localmodel/stub_server.py": Allow("a loopback-only stand-in server for tests", frozenset({"socket", "http.client", "http.server", "httpx", "urllib.request"})),
    "plugins/graph_common.py": Allow("Microsoft Graph read-only source plugin: the worker's own sign-in, off by default, https://graph.microsoft.com only",
                                     frozenset({"urllib.request"}), frozenset({"graph.microsoft.com"})),
    "proactive/fire.py": Allow("calls the local agent service to start a run the worker pressed", frozenset({"httpx"}),
                               loopback_helpers=frozenset({"agent_url"})),
    "proactive/sources.py": Allow("reads run lists from the local agent service", frozenset({"httpx"}),
                                  loopback_helpers=frozenset({"agent_url"})),
    "gitanalysis/source.py": Allow("runs read-only `git log` on a local repository; the argument list comes from git_argv(), which puts git first",
                                   dynamic_process=True),
    "gitanalysis/synth.py": Allow("builds generated local repositories for tests and demos with git; the argument lists are built by its own helpers",
                                  dynamic_process=True),
    "proactive/paths.py": Allow("home_dir() defaults to ~/.understudy (UNDERSTUDY_HOME), the same per-install state directory as the store", home_path=True),
    "cue/paths.py": Allow("home_dir() defaults to ~/.understudy (UNDERSTUDY_HOME), the same per-install state directory as the store", home_path=True),
    "plugins/manifest.py": Allow("loads a plugin's entry class from the bundled plugin directory by the module name in its manifest",
                                 dynamic_import=True),
}

AGENT_PKG = ENGINE_PKG.parents[1] / "agent" / "understudy_agent"
# Reviewed exceptions for the agent service. Key = path relative to services/agent (so it starts with understudy_agent/).
AGENT_ALLOW: dict[str, Allow] = {
    "understudy_agent/handoff_io.py": Allow("the agent's thin client for the engine API on this machine (default http://127.0.0.1:7700)", frozenset({"httpx"})),
    "understudy_agent/server.py": Allow("the agent API: health probes of the sandbox sites on loopback and uvicorn bound to 127.0.0.1; includes its "
                                        "optional routers (models, live) by module names listed in a literal tuple", frozenset({"httpx"}), dynamic_import=True),
    "understudy_agent/sandbox_sites/runner.py": Allow("serves and probes the three sandbox calculator sites on 127.0.0.1", frozenset({"socket", "httpx"}),
                                                      loopback_names=frozenset({"HOST"})),
    "understudy_agent/sandbox_roles/base.py": Allow("serves the role sandboxes (programmer, analyst workbenches) on 127.0.0.1", frozenset({"socket"}),
                                                    loopback_names=frozenset({"HOST"})),
    "understudy_agent/tiers/computer_use.py": Allow("the real-desktop actuator (off unless UNDERSTUDY_REAL_ACTUATOR=1) reads a TextEdit document with a constant "
                                                    "AppleScript; osascript is accepted only with a constant -e script that has no shell, URL, mail or fetcher",
                                                    processes=frozenset({"osascript"})),
    "understudy_agent/voice/tts.py": Allow("ElevenLabs text-to-speech (D19). NOT ACCEPTED YET: it sends free text with no purpose, no SafePayload and "
                                           "no ledger row (REVIEW-PRIVACY P1b); the LIVE agent is to route it through the ledger", frozenset({"httpx"}),
                                           frozenset({"api.elevenlabs.io"}),
                                           pending="voice text is sent to a third party outside the egress guard and ledger"),
}
AGENT_SKIP = ("understudy_agent/models/", "understudy_agent/runtime/")        # the provider package is the allowed client; runtime has its own scan

#: the models package may use provider SDKs; no reviewed entry can extend this to another file
RUNTIME_DIR = AGENT_PKG / "runtime"
RECORDERS = {"record_raw_call", "record_direct", "LedgeredPort"}


@dataclass
class GuardReport:
    files: list[str] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)
    allowed_uses: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations


def _allow_for(relpath: str, table: dict[str, Allow] | None = None) -> Allow | None:
    for pat, a in (ALLOW if table is None else table).items():
        if fnmatch.fnmatch(relpath, pat):
            return a
    return None


def _root(mod: str) -> str:
    return mod.split(".")[0]


def _host(url: str) -> str | None:
    return host_of(url)


def pending_exceptions() -> list[dict[str, str]]:
    """Reviewed-entry exceptions that are NOT accepted and wait for a fix (listed in the evaluation until they are gone)."""
    out = []
    for table in (ALLOW, AGENT_ALLOW):
        for path, a in table.items():
            if a.pending:
                out.append({"file": path, "reason": a.reason, "pending": a.pending})
    return out


def scan_source(src: str, relpath: str, *, kind: str | None = None) -> tuple[list[Violation], list[str]]:
    """Scan one module's source with the rules for its place. ``kind`` defaults from the path: a path under ``understudy_agent/runtime/``
    is the runtime, another ``understudy_agent/`` path is the agent service, anything else is an extension layer."""
    if kind is None:
        kind = "runtime" if relpath.startswith("understudy_agent/runtime/") else "agent" if relpath.startswith("understudy_agent/") else "layer"
    agent_pure = kind == "agent" and relpath.startswith(AGENT_PURE_PREFIXES)
    pure = (kind == "layer" and relpath.split("/", 1)[0] in PURE_COMPUTE_DIRS) or agent_pure
    pkg = "understudy_agent" if kind in ("agent", "runtime") else "understudy_engine"
    if agent_pure:
        kind = "layer"                               # held to the extension-layer rules (no model client, allowlisted imports), as pure compute
    allow = None if (pure or kind == "runtime") else _allow_for(relpath, AGENT_ALLOW if kind == "agent" else ALLOW)
    return analyse(src, relpath, Policy(kind=kind, pure=pure, package_root=pkg), allow)


def guarded_files(root: Path | None = None) -> list[Path]:
    root = root or ENGINE_PKG
    files: list[Path] = []
    for d in GUARDED_DIRS:
        files.extend(sorted((root / d).rglob("*.py")) if (root / d).is_dir() else [])
    for name in GUARDED_FILES:
        if (root / name).is_file():
            files.append(root / name)
    return files


def scan_tree(root: Path | None = None, files: Iterable[Path] | None = None) -> GuardReport:
    """Scan every guarded file under the engine package (or ``files``)."""
    root = root or ENGINE_PKG
    rep = GuardReport()
    for p in (list(files) if files is not None else guarded_files(root)):
        rel = p.relative_to(root).as_posix() if p.is_absolute() and root in p.parents else p.as_posix()
        rep.files.append(rel)
        viol, used = scan_source(p.read_text(encoding="utf-8"), rel)
        rep.violations.extend(viol)
        rep.allowed_uses.extend(used)
    return rep


# ----------------------------------------------------------------------------------------------------- the agent service
def scan_agent_source(src: str, relpath: str) -> tuple[list[Violation], list[str]]:
    """One agent-service module (path starting ``understudy_agent/``) under the agent rules, with its reviewed entry if it has one."""
    return scan_source(src, relpath, kind="agent")


def agent_files(root: Path | None = None) -> list[Path]:
    root = root or AGENT_PKG
    return [p for p in sorted(root.rglob("*.py")) if "__pycache__" not in p.parts]


def scan_agent(root: Path | None = None) -> GuardReport:
    """Every module of the agent service except the provider package (``models/``, the allowed client) and ``runtime/`` (its own scan).
    Unreviewed network use is a violation; a reviewed file may use only what its ``AGENT_ALLOW`` entry names."""
    root = root or AGENT_PKG
    rep = GuardReport()
    for p in agent_files(root):
        rel = f"{root.name}/{p.relative_to(root).as_posix()}"
        if rel.startswith(AGENT_SKIP):
            continue
        rep.files.append(rel)
        viol, used = scan_agent_source(p.read_text(encoding="utf-8"), rel)
        rep.violations.extend(viol)
        rep.allowed_uses.extend(used)
    return rep


# ----------------------------------------------------------------------------------------------------- the agent runtime
def scan_runtime_source(src: str, relpath: str) -> list[Violation]:
    """The agent runtime plans through ``ModelPort`` by design (parent and child steps), so it is checked by two rules: the network rules
    with no exceptions (children are sandboxed and have no network; ``netscan``), and any visible direct call to a port (``.plan``,
    ``.read``, ``.check``, ``.vision``, ``.computer_step`` on a port-like receiver) must sit in a function that also records a
    metadata-only ledger line (``record_raw_call``, ``ledger.record_direct`` or a ``LedgeredPort``). Calls that carry a SafePayload go
    through ``egress.send`` and are not direct. A call hidden inside another object (for example a safety pipeline's reader) is not
    visible to this check."""
    out: list[Violation] = list(analyse(src, relpath, Policy(kind="runtime", package_root="understudy_agent"), None)[0])
    if any(v.rule == "unparseable" for v in out):
        return out
    tree = ast.parse(src)
    for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        direct: list[ast.Call] = []
        recorded = False
        for c in ast.walk(fn):
            if not isinstance(c, ast.Call):
                continue
            f = c.func
            name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else ""
            if name in RECORDERS:
                recorded = True
            if isinstance(f, ast.Attribute):
                recv = dotted(f.value)
                last = recv.split(".")[-1] if recv else ""
                if f.attr in ALWAYS_CALLS or (f.attr in PORTISH_CALLS and PORTISH_RECEIVER.search(last)):
                    direct.append(c)
        if direct and not recorded:
            for c in direct:
                out.append(Violation(relpath, c.lineno, "unrecorded_model_call",
                                     f"{fn.name}() calls a model port directly without writing a ledger line "
                                     f"(use egress.send for payloads, or record_raw_call for the worker-requested raw path)"))
    seen = set()
    uniq = []
    for v in out:
        k = (v.file, v.line, v.rule, v.detail)
        if k not in seen:
            seen.add(k)
            uniq.append(v)
    return uniq


def scan_runtime(root: Path | None = None) -> GuardReport:
    """Scan ``services/agent/understudy_agent/runtime`` (skipped, with an empty report, when it does not exist)."""
    root = root or RUNTIME_DIR
    rep = GuardReport()
    if not root.is_dir():
        return rep
    for p in sorted(root.rglob("*.py")):
        rel = "runtime/" + p.relative_to(root).as_posix()
        rep.files.append(rel)
        rep.violations.extend(scan_runtime_source(p.read_text(encoding="utf-8"), rel))
    return rep


# ----------------------------------------------------------------------------------------------------- image endpoints (REQ-5)
REPO_ROOT = ENGINE_PKG.parents[2]
AGENT_PKG = REPO_ROOT / "services" / "agent" / "understudy_agent"
PROVIDER_HOSTS = (
    "generativelanguage.googleapis.com", "aiplatform.googleapis.com", "api.openai.com", "openai.azure.com", "api.openai",
    "api.anthropic.com", "openrouter.ai", "api.mistral.ai", "api.cohere", "api.groq.com", "api.together.xyz", "api.together.ai",
    "api.deepseek.com", "api.x.ai", "api.perplexity.ai", "api.fireworks.ai", "api.replicate.com", "inference.huggingface",
    "api-inference.huggingface.co", "bedrock-runtime", "api.ai21.com", "api.voyageai.com", "api.cerebras.ai",
)
PROVIDER_IMPORT_ROOTS = {"openai", "vertexai", "anthropic", "cohere", "mistralai", "groq", "litellm", "ollama", "together", "replicate"}
PROVIDER_IMPORT_PREFIXES = ("google.genai", "google.generativeai", "google.cloud.aiplatform", "google.ai")
#: the only Python files that may import a hosted-model client or name its API host: the provider modules, the egress module, and the
#: guard and its sample data (which hold the host names they search for)
PROVIDER_ALLOWED = ("understudy_agent/models/*", "understudy_agent/models/**/*", "understudy_engine/privacy/egress.py", "understudy_engine/privacy/guard.py",
                    "understudy_engine/privacy/guard_samples.py")


def _provider_allowed(rel: str) -> bool:
    return any(fnmatch.fnmatch(rel, pat) for pat in PROVIDER_ALLOWED)


def provider_endpoint_violations(src: str, relpath: str, *, include_agent_network: bool = True) -> list[Violation]:
    """In one Python file outside the allowed modules: any import of a model-provider client (Gemini, OpenAI, Anthropic and the other
    hosted-model SDKs), and any string (including the literal parts of an f-string) that names a hosted-model API host. For a path
    under ``understudy_agent/`` the agent network rules (``scan_agent_source``) are added, so one call answers "may this agent module
    send data to a host?"; ``scan_provider_endpoints`` passes ``include_agent_network=False`` because ``scan_agent`` reports those."""
    out: list[Violation] = []
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        return [Violation(relpath, exc.lineno or 0, "unparseable", "the file does not parse, so it cannot be checked")]
    for node in ast.walk(tree):
        mods: list[str] = []
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            mods = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
        for m in mods:
            if _root(m) in PROVIDER_IMPORT_ROOTS or m.startswith(PROVIDER_IMPORT_PREFIXES):
                out.append(Violation(relpath, node.lineno, "provider_client_import",
                                     f"imports {m}: only the models package and privacy.egress may open a Gemini or OpenAI client"))
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            low = node.value.lower()
            for h in PROVIDER_HOSTS:
                if h in low:
                    out.append(Violation(relpath, node.lineno, "provider_host", f"names the API host {h}"))
                    break
    if include_agent_network and relpath.startswith("understudy_agent/") and not relpath.startswith(AGENT_SKIP[0]):
        out.extend(scan_agent_source(src, relpath)[0] if not relpath.startswith(AGENT_SKIP[1]) else scan_runtime_source(src, relpath))
    seen: set[tuple[str, int, str, str]] = set()
    uniq = []
    for v in out:
        k = (v.file, v.line, v.rule, v.detail)
        if k not in seen:
            seen.add(k)
            uniq.append(v)
    return uniq


def scan_provider_endpoints(roots: Iterable[Path] | None = None) -> GuardReport:
    """Every production Python module of the engine and the agent service (tests excluded) except the allowed ones."""
    rep = GuardReport()
    for root in (list(roots) if roots is not None else [ENGINE_PKG, AGENT_PKG]):
        if not root.is_dir():
            continue
        for p in sorted(root.rglob("*.py")):
            rel = f"{root.name}/{p.relative_to(root).as_posix()}"
            if "__pycache__" in rel or _provider_allowed(rel):
                continue
            rep.files.append(rel)
            rep.violations.extend(provider_endpoint_violations(p.read_text(encoding="utf-8"), rel, include_agent_network=False))
    return rep


# ----------------------------------------------------------------------------------------------------- who may claim "sandbox"
import re as _re  # noqa: E402

_SANDBOX_LITERAL = _re.compile(r"""['"`]sandbox['"`]""")
#: code that sends real screen frames: it must never construct a frame or gate whose source is "sandbox" (D30)
REAL_SCREEN_PY_DIRS = ("awareness",)
REAL_SCREEN_TS_GLOBS = ("apps/desktop/src/main/awareness/**/*.ts", "apps/desktop/src/main/live-*.ts", "apps/desktop/src/main/live/**/*.ts",
                        "apps/desktop/src/renderer/live/**/*.ts", "apps/desktop/src/renderer/live/**/*.tsx")


def sandbox_claim_violations_py(src: str, relpath: str) -> list[Violation]:
    out: list[Violation] = []
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        return [Violation(relpath, exc.lineno or 0, "unparseable", "the file does not parse, so it cannot be checked")]
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value == "sandbox":
            out.append(Violation(relpath, node.lineno, "sandbox_claim", 'real-screen code may not use the string "sandbox" (image source)'))
    return out


def scan_sandbox_claims(repo: Path | None = None) -> GuardReport:
    """Nothing that sends real screen frames may construct ``sandbox``: the Python awareness code and the awareness, Live and hotkey
    TypeScript (test files are skipped, so a test may check that a sandbox claim is refused). ENFORCED by this static scan; the HTTP
    route cannot tell a local caller's claim from the truth (see ``image.frame_request_problem``), so for a local process that
    scan is the control and the ledger's ``source`` column is the audit."""
    repo = repo or REPO_ROOT
    rep = GuardReport()
    for d in REAL_SCREEN_PY_DIRS:
        base = repo / "services" / "engine" / "understudy_engine" / d
        for p in sorted(base.rglob("*.py")) if base.is_dir() else []:
            rel = p.relative_to(repo).as_posix()
            rep.files.append(rel)
            rep.violations.extend(sandbox_claim_violations_py(p.read_text(encoding="utf-8"), rel))
    seen: set[Path] = set()
    for pat in REAL_SCREEN_TS_GLOBS:
        for p in sorted(repo.glob(pat)):
            if p in seen or p.name.endswith((".test.ts", ".spec.ts", ".test.tsx", ".spec.tsx")):
                continue
            seen.add(p)
            rel = p.relative_to(repo).as_posix()
            rep.files.append(rel)
            for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if _SANDBOX_LITERAL.search(line):
                    rep.violations.append(Violation(rel, i, "sandbox_claim", 'real-screen code may not use the string "sandbox" (image source)'))
    return rep


def ts_provider_references(repo: Path | None = None) -> list[str]:
    """REPORT ONLY: TypeScript files under apps/desktop/src that name a Gemini or OpenAI API host or client package. The old project's
    code is still there behind flags; the rule is that frames reach a provider through the engine's egress guard, not from these."""
    repo = repo or REPO_ROOT
    base = repo / "apps" / "desktop" / "src"
    pats = ("generativelanguage.googleapis.com", "@google/genai", "api.openai.com", "aiplatform.googleapis.com")
    out = []
    for p in sorted(base.rglob("*.ts")) if base.is_dir() else []:
        if p.name.endswith((".test.ts", ".spec.ts")):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if any(x in text for x in pats):
            out.append(p.relative_to(repo).as_posix())
    return out
