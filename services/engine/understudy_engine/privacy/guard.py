"""Static egress guard: no module in the new layers may reach a model except through ``privacy/egress.py``.

``scan_tree()`` walks the extension layers (``calendar/``, ``gitanalysis/``, ``proactive/``, ``localmodel/``, ``plugins/`` and
their ``routes_*.py``) and reports every place that

* imports a model or network client (``openai``, ``anthropic``, ``google.*``, ``requests``, ``aiohttp``, ``httpx``,
  ``urllib.request``, ``http.client``, ``socket``, ``smtplib`` and friends),
* imports or names ``ModelPort``, ``get_model_port``, ``understudy_agent.models`` or a provider class,
* calls ``.computer_step`` or ``.vision`` on anything, or ``.plan`` / ``.check`` / ``.read`` on a receiver whose name says it
  is a port, model, provider, client or llm,
* shells out to ``curl`` or ``wget``,
* or imports a network module by a constant name through ``importlib`` / ``__import__``.

A file may use a network client only if it is in ``ALLOW`` with a reason, and then only for the URLs the entry names:
loopback hosts, an explicitly allowed host, or an f-string that starts with a named loopback helper such as ``agent_url()``.
Nothing is ever allowed to import a model client or ``ModelPort``.

Limits, stated plainly: this is a static, name-based check. It does not follow a module name held in a variable
(``importlib.import_module(name)``), it cannot see code added at run time, and it judges ``.plan`` and ``.check`` by the
receiver's name. It catches the mistakes honest code makes (importing the OpenAI SDK "just for wording"); it is not a
defence against deliberate evasion. The runtime defence is that ``egress.send`` is the only function that builds a model
request from a ``SafePayload`` and writes the ledger.
"""
from __future__ import annotations

import ast
import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

ENGINE_PKG = Path(__file__).resolve().parents[1]
GUARDED_DIRS = ("calendar", "gitanalysis", "proactive", "localmodel", "plugins")
GUARDED_FILES = ("routes_calendar.py", "routes_git.py", "routes_localmodel.py", "routes_proactive.py", "routes_plugins.py")

MODEL_ROOTS = {
    "openai", "anthropic", "google", "cohere", "mistralai", "groq", "litellm", "langchain", "langchain_openai", "ollama",
    "together", "replicate", "vertexai", "transformers",
}
NETWORK_MODULES = {
    "requests", "aiohttp", "urllib3", "httplib2", "websockets", "websocket", "pycurl", "grpc", "boto3", "httpx", "urllib.request",
    "http.client", "socket", "ssl", "smtplib", "ftplib", "imaplib", "poplib", "telnetlib", "xmlrpc.client",
}
MODEL_NAMES = {"ModelPort", "get_model_port", "OpenAIProvider", "GeminiProvider", "MockProvider", "reset_model_port"}
MODEL_PACKAGES = ("understudy_agent.models",)
ALWAYS_CALLS = {"computer_step", "vision"}
PORTISH_CALLS = {"plan", "check", "read"}
PORTISH_RECEIVER = re.compile(r"port|model|provider|llm|openai|client", re.I)
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}
SHELL_FETCHERS = ("curl", "wget")


@dataclass(frozen=True)
class Allow:
    """Why a guarded file may open a network connection, and to where."""

    reason: str
    imports: frozenset[str] = frozenset()
    hosts: frozenset[str] = frozenset()                 # remote hosts its URL literals may name (besides loopback)
    loopback_helpers: frozenset[str] = frozenset()      # f"{helper()}/path" is loopback by construction
    loopback_names: frozenset[str] = frozenset()        # f"http://{name}:..." where ``name`` is a constant checked to be loopback


# Reviewed exceptions. Key = path relative to the engine package, glob allowed. Add an entry only with a reason a reviewer accepts.
ALLOW: dict[str, Allow] = {
    "localmodel/client.py": Allow("talks to llama-server on this machine only; assert_loopback() refuses any other host", frozenset({"httpx"})),
    "localmodel/server.py": Allow("starts and probes llama-server on a loopback port", frozenset({"socket", "httpx", "urllib.request", "http.client"}),
                                  loopback_names=frozenset({"config.HOST"})),
    "localmodel/stub_server.py": Allow("a loopback-only stand-in server for tests", frozenset({"socket", "http.client", "httpx", "urllib.request"})),
    "plugins/graph_common.py": Allow("Microsoft Graph read-only source plugin: the worker's own sign-in, off by default, https://graph.microsoft.com only",
                                     frozenset({"urllib.request"}), frozenset({"graph.microsoft.com"})),
    "proactive/fire.py": Allow("calls the local agent service to start a run the worker pressed", frozenset({"httpx"}),
                               loopback_helpers=frozenset({"agent_url"})),
    "proactive/sources.py": Allow("reads run lists from the local agent service", frozenset({"httpx"}),
                                  loopback_helpers=frozenset({"agent_url"})),
}


@dataclass(frozen=True)
class Violation:
    file: str
    line: int
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line}: {self.rule}: {self.detail}"


@dataclass
class GuardReport:
    files: list[str] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)
    allowed_uses: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations


def _allow_for(relpath: str) -> Allow | None:
    for pat, a in ALLOW.items():
        if fnmatch.fnmatch(relpath, pat):
            return a
    return None


def _root(mod: str) -> str:
    return mod.split(".")[0]


def _host(url: str) -> str | None:
    m = re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://(\[[^\]]+\]|[^/:?#\s{}]*)", url)
    return m.group(1).lower() if m else None


def _dotted(node: ast.AST) -> str:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    elif isinstance(node, ast.Call):
        parts.append(_dotted(node.func) + "()")
    return ".".join(reversed(parts))


def scan_source(src: str, relpath: str) -> tuple[list[Violation], list[str]]:
    """Scan one module's source. Returns (violations, notes about allowed uses)."""
    allow = _allow_for(relpath)
    out: list[Violation] = []
    used: list[str] = []
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        return [Violation(relpath, exc.lineno or 0, "unparseable", "the file does not parse, so it cannot be checked")], used

    def bad(node: ast.AST, rule: str, detail: str) -> None:
        out.append(Violation(relpath, getattr(node, "lineno", 0), rule, detail))

    def check_module(node: ast.AST, mod: str) -> None:
        if mod.startswith(MODEL_PACKAGES) or _root(mod) in MODEL_ROOTS:
            bad(node, "model_client_import", f"imports {mod}; send through privacy.egress.send instead")
            return
        for net in NETWORK_MODULES:
            if mod == net or mod.startswith(net + "."):
                if allow and net in allow.imports:
                    used.append(f"{relpath}: {net} ({allow.reason})")
                else:
                    bad(node, "network_import", f"imports {mod}; extension layers may not open network connections "
                                                f"(add a reviewed entry to guard.ALLOW if this is not a model client)")
                return

    class V(ast.NodeVisitor):
        def visit_Import(self, node: ast.Import) -> None:
            for a in node.names:
                check_module(node, a.name)
                if a.name.split(".")[-1] in MODEL_NAMES:
                    bad(node, "model_port_name", f"imports {a.name}")

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            mod = ("." * node.level) + (node.module or "")
            if node.level == 0 and node.module:
                check_module(node, node.module)
            for a in node.names:
                if a.name in MODEL_NAMES:
                    bad(node, "model_port_name", f"imports {a.name} from {mod or '.'}")

        def visit_Name(self, node: ast.Name) -> None:
            if node.id in MODEL_NAMES:
                bad(node, "model_port_name", f"uses {node.id}")

        def visit_Attribute(self, node: ast.Attribute) -> None:
            if node.attr in MODEL_NAMES:
                bad(node, "model_port_name", f"uses .{node.attr}")
            self.generic_visit(node)

        def visit_Call(self, node: ast.Call) -> None:
            f = node.func
            if isinstance(f, ast.Attribute):
                recv = _dotted(f.value)
                if f.attr in ALWAYS_CALLS:
                    bad(node, "model_call", f"calls .{f.attr}() on {recv or 'an object'}")
                elif f.attr in PORTISH_CALLS and PORTISH_RECEIVER.search(recv.split(".")[-1] if recv else ""):
                    bad(node, "model_call", f"calls {recv}.{f.attr}(): model calls go through privacy.egress.send")
            name = _dotted(f)
            if name.endswith(("import_module", "__import__")) and node.args and isinstance(node.args[0], ast.Constant) \
                    and isinstance(node.args[0].value, str):
                check_module(node, node.args[0].value)
            self.generic_visit(node)

        def visit_Constant(self, node: ast.Constant) -> None:
            v = node.value
            if isinstance(v, str):
                if v in SHELL_FETCHERS or v.startswith(tuple(s + " " for s in SHELL_FETCHERS)):
                    bad(node, "shell_fetch", f"mentions {v.split()[0]} as a command")
                h = _host(v)
                # A URL literal only matters where a network client is allowed at all (elsewhere the import is already a
                # violation); documentation and schema ids in other files are not egress.
                if allow and h is not None and h not in LOOPBACK_HOSTS and "{" not in h and not relpath_in_docstring(node):
                    if h in allow.hosts:
                        used.append(f"{relpath}: host {h}")
                    else:
                        bad(node, "remote_url", f"a URL literal names the host {h}")

        def visit_JoinedStr(self, node: ast.JoinedStr) -> None:
            first = node.values[0] if node.values else None
            if allow and isinstance(first, ast.Constant) and isinstance(first.value, str) and "://" in first.value:
                h = _host(first.value)
                second = ast.unparse(node.values[1].value) if len(node.values) > 1 and isinstance(node.values[1], ast.FormattedValue) else ""
                if not h and second in allow.loopback_names and re.fullmatch(r"[a-zA-Z][a-zA-Z0-9+.\-]*://", first.value):
                    used.append(f"{relpath}: URL host from {second}")
                elif not h or (h not in LOOPBACK_HOSTS and h not in allow.hosts):
                    bad(node, "remote_url", "an f-string URL does not start with a loopback or allowed host literal")
                for v in node.values[1:]:
                    self.visit(v) if isinstance(v, ast.FormattedValue) else None
                return
            if isinstance(first, ast.FormattedValue) and any(isinstance(v, ast.Constant) and isinstance(v.value, str) and v.value.startswith("/")
                                                              for v in node.values[1:2]):
                # f"{base}/path": fine only if base is a named loopback helper (or an attribute of the checked loopback client)
                src_first = ast.unparse(first.value)
                helpers = allow.loopback_helpers if allow else frozenset()
                if any(h + "(" in src_first for h in helpers):
                    used.append(f"{relpath}: URL from {src_first}")
            self.generic_visit(node)

    docstring_nodes = {id(n.body[0].value) for n in ast.walk(tree) if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef))
                       and n.body and isinstance(n.body[0], ast.Expr) and isinstance(getattr(n.body[0], "value", None), ast.Constant)}

    def relpath_in_docstring(node: ast.AST) -> bool:
        return id(node) in docstring_nodes

    V().visit(tree)
    return out, used


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
