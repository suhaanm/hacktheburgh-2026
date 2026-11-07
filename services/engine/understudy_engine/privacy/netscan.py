"""The static analyser behind ``guard.py``: finds the *capability* to reach the network, a model, or another process, not just the
obvious import.

What it resolves (all by the syntax tree, nothing is executed):

* **aliases**: ``import urllib`` then ``urllib.request.urlopen``; ``from urllib import request``; ``import urllib.request as u``;
  ``from socket import socket as s``; names bound by plain assignment (``u = urllib.request``), including through
  ``importlib.import_module('...')``, ``__import__('...')``, ``getattr(mod, 'name')`` and ``builtins.__import__``;
* **constant folding** of strings built at the call site: ``'op' + 'enai'``, ``''.join(['c', 'url'])``, f-string and ``.format``
  prefixes, and module-level names assigned a constant once, so ``'c' + 'url -d ' + data`` is still ``curl``;
* **processes**: ``subprocess.*``, ``os.system``, ``os.popen``, ``os.exec*``, ``os.spawn*``, ``pty.spawn`` and
  ``asyncio.create_subprocess_*`` whose arguments name a fetcher (``curl``, ``wget``, ``nc``, ``ssh``, ``scp``, ``rsync``,
  ``osascript`` ...) by any path, carry a URL, run ``git push|fetch|pull|ls-remote``, or hand ``-c`` code to Python or a shell (that
  code is parsed and analysed in turn);
* **dynamic code**: ``exec``, ``eval``, ``compile`` of a constant string (analysed) or of anything else (a violation), and
  ``importlib.import_module`` / ``__import__`` of a name that cannot be folded;
* **network by method name**: ``create_connection``, ``open_connection``, ``getaddrinfo`` ... on any receiver;
* **servers**: ``host=`` or ``bind`` to a wildcard address.

A file in an ``Allow`` entry may use only what the entry names, and a network client in such a file must be *demonstrably loopback*:
the module must carry a literal ``127.0.0.1`` / ``localhost`` (or a named loopback constant listed in the entry), or the entry must
name the one remote host and the module must carry it. Nothing in an entry can allow a model client, ``ModelPort`` or ``ctypes``
in a pure-compute layer.

Limits, stated plainly: it is static. A value computed at run time (read from a file, the environment, ``chr()`` arithmetic, a
base64 blob) is not folded, so a string hidden that way is not seen; the unfoldable *arguments* of the dangerous calls are flagged
instead (``dynamic_import``, ``dynamic_code``). It catches honest mistakes and the common evasions; it is not a sandbox. The
runtime control is that ``egress.send`` and ``egress.send_image`` are the only functions that send content, and the ledger.
"""
from __future__ import annotations

import ast
import fnmatch
import re
from dataclasses import dataclass
from typing import Any

MODEL_ROOTS = {
    "openai", "anthropic", "google", "cohere", "mistralai", "groq", "litellm", "langchain", "langchain_openai", "ollama",
    "together", "replicate", "vertexai", "transformers",
}
#: ``google`` alone is not a violation (``google.protobuf``); these prefixes are
GOOGLE_MODEL_PREFIXES = ("google.genai", "google.generativeai", "google.cloud.aiplatform", "google.ai", "google.cloud.language", "google.cloud.vision")
MODEL_PACKAGES = ("understudy_agent.models",)
MODEL_NAMES = {"ModelPort", "get_model_port", "OpenAIProvider", "GeminiProvider", "MockProvider", "reset_model_port"}

#: modules and attributes that open or accept connections (prefix match on the resolved dotted name)
NETWORK_PREFIXES = (
    "requests", "aiohttp", "urllib3", "httplib2", "websockets", "websocket", "pycurl", "grpc", "boto3", "botocore", "httpx", "paramiko",
    "fabric", "pexpect", "scapy", "twisted", "tornado", "zmq", "pika", "redis", "kafka", "slack_sdk", "telegram", "discord", "dropbox",
    "urllib.request", "urllib.robotparser", "http.client", "http.server", "socket", "socketserver", "ssl", "smtplib", "smtpd", "ftplib",
    "imaplib", "poplib", "nntplib", "telnetlib", "xmlrpc.client", "xmlrpc.server",
    "logging.handlers.HTTPHandler", "logging.handlers.SocketHandler", "logging.handlers.DatagramHandler", "logging.handlers.SMTPHandler",
    "logging.handlers.SysLogHandler", "logging.handlers.QueueHandler",
    "multiprocessing.connection", "multiprocessing.managers",
    "asyncio.open_connection", "asyncio.start_server", "asyncio.open_unix_connection", "asyncio.start_unix_server", "asyncio.streams",
    "asyncio.sslproto", "asyncio.selector_events", "asyncio.base_events.BaseEventLoop.create_connection",
    "webbrowser", "ctypes", "cffi",
)
#: ``QueueHandler`` only forwards to a queue: not network by itself; kept out of the list above on purpose
NETWORK_PREFIXES = tuple(p for p in NETWORK_PREFIXES if p != "logging.handlers.QueueHandler")
#: method names that open a connection whatever the receiver is called (a loop, a transport, an alias the resolver lost)
NETWORK_METHODS = {"create_connection", "create_datagram_endpoint", "create_unix_connection", "sock_connect", "open_connection",
                   "getaddrinfo", "gethostbyname", "gethostbyname_ex", "getnameinfo"}
PURE_BANNED = {"subprocess", "webbrowser", "ctypes", "pty", "pexpect", "paramiko", "fabric", "cffi"}
PURE_BANNED_CALLS = {"os.system", "os.popen", "os.execv", "os.execve", "os.execvp", "os.execl", "os.execlp", "os.spawnl", "os.spawnv",
                     "os.startfile", "pty.spawn"}

PROCESS_PREFIXES = ("subprocess.", "commands.")
PROCESS_FUNCS = {"os.system", "os.popen", "os.execv", "os.execve", "os.execvp", "os.execvpe", "os.execl", "os.execle", "os.execlp",
                 "os.execlpe", "os.spawnl", "os.spawnle", "os.spawnlp", "os.spawnv", "os.spawnve", "os.spawnvp", "os.startfile", "pty.spawn",
                 "asyncio.create_subprocess_exec", "asyncio.create_subprocess_shell", "asyncio.subprocess.create_subprocess_exec",
                 "asyncio.subprocess.create_subprocess_shell"}
#: positional arguments are the command itself (not a list)
VARARG_PROCESS = {"os.execl", "os.execle", "os.execlp", "os.execlpe", "os.spawnl", "os.spawnle", "os.spawnlp", "asyncio.create_subprocess_exec",
                  "asyncio.subprocess.create_subprocess_exec"}

#: a process whose name is one of these is a fetcher (any path, any case)
FETCHERS = {"curl", "wget", "nc", "ncat", "netcat", "scp", "sftp", "ssh", "rsync", "telnet", "ftp", "tftp", "socat", "osascript", "openssl",
            "nmap", "dig", "nslookup", "host", "ping", "traceroute", "mosh", "lftp", "aria2c", "httpie", "http", "https", "xh"}
#: a bare string constant equal to one of these, in a module that starts processes, counts as naming a fetcher
BARE_FETCHERS = {"curl", "wget", "nc", "ncat", "netcat", "scp", "sftp", "ssh", "rsync", "telnet", "socat", "osascript", "openssl", "aria2c"}
WRAPPERS = {"env", "sudo", "nice", "nohup", "timeout", "time", "xargs", "command", "exec", "arch", "stdbuf", "caffeinate", "setsid", "doas"}
GIT_NETWORK = {"push", "fetch", "pull", "ls-remote", "remote", "submodule", "send-pack", "fetch-pack", "http-fetch", "daemon", "archive"}
PYTHON_NAMES = re.compile(r"^(python[0-9.]*|py|pypy[0-9.]*)$")
SHELL_NAMES = {"sh", "bash", "zsh", "dash", "ksh", "fish", "cmd", "powershell", "pwsh"}
SCP_STYLE = re.compile(r"^[\w.\-]+@[\w.\-]+:[^\s]*")

IMPORT_FUNCS = {"importlib.import_module", "importlib.__import__", "builtins.__import__", "__import__", "runpy.run_module", "pkgutil.resolve_name"}
CODE_FUNCS = {"exec", "eval", "compile", "builtins.exec", "builtins.eval", "builtins.compile"}

PORTISH_CALLS = {"plan", "check", "read"}
ALWAYS_CALLS = {"computer_step", "vision"}
PORTISH_RECEIVER = re.compile(r"port|model|provider|llm|openai|client", re.I)
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}
WILDCARD_HOSTS = {"0.0.0.0", "", "::", "*"}
LOOPBACK_WORDS = ("127.0.0.1", "localhost", "[::1]")


@dataclass(frozen=True)
class Violation:
    file: str
    line: int
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line}: {self.rule}: {self.detail}"


@dataclass(frozen=True)
class Allow:
    """Why a file may use the network (or load code dynamically), and exactly what it may use."""

    reason: str
    imports: frozenset[str] = frozenset()
    hosts: frozenset[str] = frozenset()                 # the remote hosts its URL literals may name (besides loopback)
    loopback_helpers: frozenset[str] = frozenset()      # f"{helper()}/path" is loopback by construction
    loopback_names: frozenset[str] = frozenset()        # a name whose value is a loopback constant (verified by a test)
    dynamic_import: bool = False                        # may import a module by a name it cannot fold (a plugin loader)
    dynamic_code: bool = False
    pending: str | None = None                          # an exception that is NOT accepted: it is listed until it is fixed


def host_of(url: str) -> str | None:
    m = re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://(?:[^/@\s]*@)?(\[[^\]]+\]|[^/:?#\s{}]*)", url)
    return m.group(1).lower() if m else None


def dotted(node: ast.AST) -> str:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    elif isinstance(node, ast.Call):
        parts.append(dotted(node.func) + "()")
    return ".".join(reversed(parts))


def _under(q: str, prefix: str) -> bool:
    return q == prefix or q.startswith(prefix + ".")


def _basename(token: str) -> str:
    t = token.strip().strip("'\"")
    return t.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower().removesuffix(".exe")


# ---------------------------------------------------------------------------------------------------------- the analyser
@dataclass
class Policy:
    """What a scan forbids. ``layer``: an extension layer (no model, no network, no process abuse). ``agent``: the agent service
    (network and process rules; the model port is its job). ``runtime``: the agent runtime (no network at all, unrecorded model calls)."""

    kind: str = "layer"
    pure: bool = False
    package_root: str = "understudy_engine"


class Analyzer(ast.NodeVisitor):
    def __init__(self, src: str, relpath: str, policy: Policy, allow: Allow | None, *, depth: int = 0, line_offset: int | None = None) -> None:
        self.src, self.relpath, self.policy, self.allow, self.depth = src, relpath, policy, allow, depth
        self.line_offset = line_offset
        self.out: list[Violation] = []
        self.used: list[str] = []
        self._seen: set[tuple[int, str, str]] = set()
        self.alias: dict[str, str] = {}
        self.consts: dict[str, ast.AST] = {}
        self.docstrings: set[int] = set()
        self.has_process = False
        self.loopback_evidence = False
        self.host_evidence: set[str] = set()
        self.network_used: set[str] = set()
        self._folded_binops: set[int] = set()

    # ---- reporting
    def bad(self, node: ast.AST | int, rule: str, detail: str) -> None:
        line = self.line_offset if self.line_offset is not None else (node if isinstance(node, int) else getattr(node, "lineno", 0))
        key = (line, rule, detail)
        if key in self._seen:
            return
        self._seen.add(key)
        self.out.append(Violation(self.relpath, line, rule, detail))

    # ---- entry
    def run(self) -> "Analyzer":
        try:
            tree = ast.parse(self.src)
        except SyntaxError as exc:
            self.bad(exc.lineno or 0, "unparseable", "the file does not parse, so it cannot be checked")
            return self
        self.docstrings = {id(n.body[0].value) for n in ast.walk(tree)
                           if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)) and n.body
                           and isinstance(n.body[0], ast.Expr) and isinstance(getattr(n.body[0], "value", None), ast.Constant)}
        self._bind(tree)
        self.has_process = any(isinstance(n, ast.Call) and self._is_process(self.qualify(n.func)) for n in ast.walk(tree))
        self.visit(tree)
        self._finish()
        return self

    # ---- aliases and constants
    def _abs_module(self, level: int, module: str | None) -> str:
        if not level:
            return module or ""
        parts = self.relpath[:-3].split("/") if self.relpath.endswith(".py") else self.relpath.split("/")
        if not parts or parts[0] != self.policy.package_root:
            parts = [self.policy.package_root] + parts
        pkg = parts[:-1]
        base = pkg[: max(0, len(pkg) - (level - 1))]
        return ".".join(base + ([module] if module else []))

    def _bind(self, tree: ast.AST) -> None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.asname:
                        self.alias[a.asname] = a.name
                    else:
                        self.alias[a.name.split(".")[0]] = a.name.split(".")[0]
            elif isinstance(node, ast.ImportFrom):
                mod = self._abs_module(node.level, node.module)
                for a in node.names:
                    if a.name != "*":
                        self.alias[a.asname or a.name] = f"{mod}.{a.name}" if mod else a.name
        # names assigned once to a foldable constant, and aliases of modules and attributes (two passes reach `b = a; c = b`)
        counts: dict[str, int] = {}
        assigns: list[tuple[str, ast.AST]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                counts[node.targets[0].id] = counts.get(node.targets[0].id, 0) + 1
                assigns.append((node.targets[0].id, node.value))
            elif isinstance(node, (ast.AugAssign, ast.AnnAssign)) and isinstance(node.target, ast.Name):
                counts[node.target.id] = counts.get(node.target.id, 0) + 2
        for name, value in assigns:
            if counts.get(name) == 1:
                self.consts[name] = value
        for _ in range(2):
            for name, value in assigns:
                q = self.qualify(value)
                if q and counts.get(name) == 1 and name not in self.alias:
                    self.alias[name] = q

    # ---- resolution
    def qualify(self, node: ast.AST) -> str | None:
        """The dotted module or attribute this expression refers to, through aliases, ``import_module``, ``__import__`` and ``getattr``."""
        if isinstance(node, ast.Name):
            return self.alias.get(node.id) or (node.id if node.id in ("__import__", "exec", "eval", "compile", "getattr", "open") else None)
        if isinstance(node, ast.Attribute):
            base = self.qualify(node.value)
            return f"{base}.{node.attr}" if base else None
        if isinstance(node, ast.Subscript):
            if isinstance(node.value, ast.Name) and node.value.id == "__builtins__":
                key = self.fold(node.slice)
                if key[1]:
                    return f"builtins.{key[0]}"
            return None
        if isinstance(node, ast.Call):
            f = self.qualify(node.func)
            if f in IMPORT_FUNCS and node.args:
                name, ok = self.fold(node.args[0])
                return name if ok and name else None
            if f in ("getattr", "builtins.getattr") and len(node.args) >= 2:
                base = self.qualify(node.args[0])
                attr, ok = self.fold(node.args[1])
                if base and ok and attr:
                    return f"{base}.{attr}"
            return None
        return None

    def fold(self, node: ast.AST, depth: int = 0) -> tuple[str, bool]:
        """(the constant string this expression starts with, whether that is all of it)."""
        if depth > 12:
            return "", False
        if isinstance(node, ast.Constant):
            return (node.value, True) if isinstance(node.value, str) else (("", False) if not isinstance(node.value, bytes) else (node.value.decode("utf-8", "replace"), True))
        if isinstance(node, ast.JoinedStr):
            out = ""
            for v in node.values:
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    out += v.value
                else:
                    return out, False
            return out, True
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left, lok = self.fold(node.left, depth + 1)
            if not lok:
                return left, False
            right, rok = self.fold(node.right, depth + 1)
            return left + right, rok
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
            left, lok = self.fold(node.left, depth + 1)
            return left.split("%", 1)[0], False if "%" in left or not lok else lok
        if isinstance(node, ast.Name) and node.id in self.consts and node.id not in self.alias:
            return self.fold(self.consts[node.id], depth + 1)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "join" and node.args:
                sep, sok = self.fold(node.func.value, depth + 1)
                if sok and isinstance(node.args[0], (ast.List, ast.Tuple)):
                    parts = [self.fold(e, depth + 1) for e in node.args[0].elts]
                    out, complete = "", True
                    for i, (p, ok) in enumerate(parts):
                        out += (sep if i else "") + p
                        if not ok:
                            return out, False
                    return out, complete
            if node.func.attr == "format":
                base, ok = self.fold(node.func.value, depth + 1)
                return base.split("{", 1)[0], False if "{" in base or not ok else ok
            if node.func.attr in ("lower", "upper", "strip", "casefold", "title"):
                base, ok = self.fold(node.func.value, depth + 1)
                return getattr(base, node.func.attr)(), ok
        return "", False

    # ---- checks on a resolved dotted name
    def _model_check(self, node: ast.AST, q: str, via: str) -> bool:
        sdk = q.split(".")[0] in MODEL_ROOTS - {"google"} or any(_under(q, p) for p in GOOGLE_MODEL_PREFIXES)
        # the agent service and its runtime ARE the model port's callers; only an extension layer may not touch it at all
        hit = sdk or (self.policy.kind == "layer" and any(q.startswith(p) for p in MODEL_PACKAGES))
        if hit:
            self.bad(node, "model_client_import", f"{via} {q}; model calls go through privacy.egress.send")
            return True
        return False

    def _allowed_import(self, q: str) -> bool:
        if not self.allow:
            return False
        return any(_under(q, a) or _under(a, q) for a in self.allow.imports)

    def _check_name(self, node: ast.AST, q: str, via: str) -> None:
        """Flag a resolved dotted name that is a model client, a pure-compute violation or a network capability."""
        if self.policy.pure and q.split(".")[0] in PURE_BANNED:
            self.bad(node, "pure_compute_import", f"{via} {q}; this layer is pure computation (no processes, no network, no model)")
            return
        if self._model_check(node, q, via):
            return
        for p in NETWORK_PREFIXES:
            if _under(q, p):
                if self.policy.kind == "runtime" or self.policy.pure or not self._allowed_import(q):
                    self.bad(node, "network_import", f"{via} {q}: this code may not open network connections"
                             + ("" if self.policy.kind in ("runtime",) or self.policy.pure else " (add a reviewed entry to the guard's allow list if it is not a model client)"))
                else:
                    self.network_used.add(p)
                    self.used.append(f"{self.relpath}: {p} ({self.allow.reason})" if self.allow else "")
                return

    # ---- visiting
    def visit_Import(self, node: ast.Import) -> None:
        for a in node.names:
            self._check_name(node, a.name, "imports")
            if a.name.split(".")[-1] in MODEL_NAMES and self.policy.kind == "layer":
                self.bad(node, "model_port_name", f"imports {a.name}")

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        mod = self._abs_module(node.level, node.module)
        if mod:
            self._check_name(node, mod, "imports")
        for a in node.names:
            if a.name == "*":
                continue
            self._check_name(node, f"{mod}.{a.name}" if mod else a.name, "imports")
            if a.name in MODEL_NAMES and self.policy.kind == "layer":
                self.bad(node, "model_port_name", f"imports {a.name} from {mod or '.'}")

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in MODEL_NAMES and self.policy.kind == "layer":
            self.bad(node, "model_port_name", f"uses {node.id}")
        if self.allow and (node.id in self.allow.loopback_names):
            self.loopback_evidence = True

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in MODEL_NAMES and self.policy.kind == "layer":
            self.bad(node, "model_port_name", f"uses .{node.attr}")
        q = self.qualify(node)
        if q:
            self._check_name(node, q, "uses")
        if self.allow and dotted(node) in self.allow.loopback_names:
            self.loopback_evidence = True
        self.generic_visit(node)

    def _is_process(self, q: str | None) -> bool:
        return bool(q) and (q in PROCESS_FUNCS or any(q.startswith(p) for p in PROCESS_PREFIXES))

    def visit_Call(self, node: ast.Call) -> None:
        q = self.qualify(node.func)
        f = node.func
        meth = f.attr if isinstance(f, ast.Attribute) else None
        if meth is None and isinstance(f, ast.Call):                       # getattr(obj, 'plan')(...)
            gf = self.qualify(f.func)
            if gf in ("getattr", "builtins.getattr") and len(f.args) >= 2:
                name, ok = self.fold(f.args[1])
                if ok:
                    meth = name
        if q and self.policy.pure and (q in PURE_BANNED_CALLS):
            self.bad(node, "pure_compute_call", f"calls {q}(); this layer is pure computation")
        if self._is_process(q):
            self._process_call(node, q or "")
        if (q in IMPORT_FUNCS) or (isinstance(f, ast.Name) and f.id == "__import__" and "__import__" not in self.alias):
            self._import_call(node)
        if (q in CODE_FUNCS) or (isinstance(f, ast.Name) and f.id in ("exec", "eval", "compile") and f.id not in self.alias):
            self._code_call(node, q or (f.id if isinstance(f, ast.Name) else ""))
        if meth in NETWORK_METHODS and not (self.allow and any(_under(a, "socket") or _under(a, "asyncio") for a in self.allow.imports)):
            self.bad(node, "network_call", f"calls .{meth}(): this code may not open network connections")
        if self.policy.kind == "layer" and meth is not None:
            self._model_call(node, meth, dotted(f.value) if isinstance(f, ast.Attribute) else "")
        self._server_call(node, q)
        if self.allow and q and any(q.endswith(h + "()") or q == h for h in self.allow.loopback_helpers):
            self.loopback_evidence = True
        if self.allow and dotted(node.func).split("(")[0].rsplit(".", 1)[-1] in self.allow.loopback_helpers:
            self.loopback_evidence = True
        self.generic_visit(node)

    # ---- model calls (extension layers only: the agent's own job is to call the port)
    def _model_call(self, node: ast.Call, meth: str, recv: str) -> None:
        last = recv.split(".")[-1] if recv else ""
        if meth in ALWAYS_CALLS or meth == "plan":
            self.bad(node, "model_call", f"calls .{meth}(){f' on {recv}' if recv else ''}: model calls go through privacy.egress.send")
            return
        if meth in ("check", "read"):
            kwnames = {k.arg for k in node.keywords if k.arg}
            schemaish = bool(kwnames & {"schema", "messages", "untrusted", "prompt"})
            if len(node.args) >= 2:
                a1 = node.args[1]
                schemaish = schemaish or isinstance(a1, ast.Dict) or "schema" in dotted(a1).lower() or (isinstance(a1, ast.Name) and "schema" in a1.id.lower())
            if node.args and isinstance(node.args[0], ast.List) and node.args[0].elts and isinstance(node.args[0].elts[0], ast.Dict):
                schemaish = schemaish or any(isinstance(k, ast.Constant) and k.value == "role" for k in node.args[0].elts[0].keys)
            if PORTISH_RECEIVER.search(last) or schemaish:
                self.bad(node, "model_call", f"calls {recv + '.' if recv else '.'}{meth}(): model calls go through privacy.egress.send")

    # ---- servers
    def _server_call(self, node: ast.Call, q: str | None) -> None:
        for k in node.keywords:
            if k.arg == "host":
                if isinstance(k.value, ast.Constant) and isinstance(k.value.value, str):
                    if k.value.value in WILDCARD_HOSTS:
                        self.bad(node, "server_not_loopback", f"listens on {k.value.value or 'every interface'}; bind to 127.0.0.1")
                    elif k.value.value in LOOPBACK_HOSTS:
                        self.loopback_evidence = True
        f = node.func
        if isinstance(f, ast.Attribute) and f.attr in ("bind", "connect", "connect_ex", "sendto") and node.args and isinstance(node.args[0], ast.Tuple) and node.args[0].elts:
            h = node.args[0].elts[0]
            if isinstance(h, ast.Constant) and isinstance(h.value, str):
                if h.value in WILDCARD_HOSTS and f.attr == "bind":
                    self.bad(node, "server_not_loopback", "binds a socket to every interface; bind to 127.0.0.1")

    # ---- dynamic import and code
    def _import_call(self, node: ast.Call) -> None:
        if not node.args:
            return
        name, ok = self.fold(node.args[0])
        if ok and name:
            self._check_name(node, name, "imports dynamically")
            if name.split(".")[-1] in MODEL_NAMES and self.policy.kind == "layer":
                self.bad(node, "model_port_name", f"imports {name} dynamically")
        elif not (self.allow and self.allow.dynamic_import):
            self.bad(node, "dynamic_import", "imports a module by a name this check cannot resolve; a reviewed entry may allow a plugin loader")

    def _code_call(self, node: ast.Call, name: str) -> None:
        if not node.args:
            return
        code, ok = self.fold(node.args[0])
        if ok and code and self.depth < 3:
            self._scan_child_code(node, code)
        elif name.split(".")[-1] == "compile":
            return                       # compiling is not running: an exec() of the result is flagged where it happens
        elif not (self.allow and self.allow.dynamic_code):
            self.bad(node, "dynamic_code", f"{name.split('.')[-1]}() of code this check cannot read; reviewed code does not need it")

    def _scan_child_code(self, node: ast.AST, code: str) -> None:
        try:
            ast.parse(code)
        except SyntaxError:
            try:
                ast.parse(code, mode="eval")
            except SyntaxError:
                return
        child = Analyzer(code, self.relpath, self.policy, self.allow, depth=self.depth + 1, line_offset=getattr(node, "lineno", 0)).run()
        for v in child.out:
            self.bad(node, v.rule, f"in code run from here: {v.detail}")

    # ---- processes
    def _process_call(self, node: ast.Call, q: str) -> None:
        elems: list[tuple[str, bool]] = []
        if q in VARARG_PROCESS or q.startswith("os.spawn") and q.endswith(("l", "le", "lp")):
            args = list(node.args[1:] if q.startswith("os.spawn") else node.args)
            elems = [self._elem(a) for a in args]
        else:
            a0: ast.AST | None = node.args[0] if node.args else next((k.value for k in node.keywords if k.arg == "args"), None)
            if isinstance(a0, ast.Name) and a0.id in self.consts:
                a0 = self.consts[a0.id]
            if isinstance(a0, (ast.List, ast.Tuple)):
                elems = [self._elem(e) for e in a0.elts]
            elif a0 is not None:
                pre, ok = self.fold(a0)
                if pre:
                    elems = [(t, True) for t in pre.split()] + ([("", False)] if not ok else [])
        texts = [e for e, _ in elems]
        binary = None
        i = 0
        while i < len(texts):
            t = texts[i]
            b = _basename(t)
            if b in WRAPPERS or t.startswith("-") or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t):
                i += 1
                continue
            binary = b
            break
        if binary in FETCHERS:
            self.bad(node, "process_fetcher", f"starts {binary}, a program that moves data over a network")
        if binary == "git":
            rest = [t for t in texts[i + 1:]]
            sub, k = None, 0
            while k < len(rest):
                if rest[k] in ("-C", "-c", "--git-dir", "--work-tree", "--exec-path"):
                    k += 2
                    continue
                if rest[k].startswith("-"):
                    k += 1
                    continue
                sub = rest[k]
                break
            if sub in GIT_NETWORK:
                self.bad(node, "process_git_network", f"runs git {sub}, which talks to a remote")
        for t in texts:
            if "://" in t or SCP_STYLE.match(t):
                self.bad(node, "process_url", "hands a URL or remote address to a process")
                break
        if binary and (PYTHON_NAMES.match(binary) or binary in SHELL_NAMES) and "-c" in texts:
            j = texts.index("-c")
            if j + 1 < len(elems):
                code, ok = elems[j + 1]
                if ok and code and self.depth < 3:
                    if binary in SHELL_NAMES:
                        self._shell_string(node, code)
                    else:
                        self._scan_child_code(node, code)
                elif not ok:
                    self.bad(node, "process_code", f"hands {binary} -c code this check cannot read")

    def _elem(self, e: ast.AST) -> tuple[str, bool]:
        """One element of a command line; ``sys.executable`` is the Python interpreter."""
        text, ok = self.fold(e)
        if not ok and self.qualify(e) == "sys.executable":
            return "python", True
        return text, ok

    def _shell_string(self, node: ast.AST, cmd: str) -> None:
        toks = cmd.replace(";", " ").replace("&&", " ").replace("|", " ").split()
        for i, t in enumerate(toks):
            if _basename(t) in FETCHERS and (i == 0 or toks[i - 1] in ("&", "&&", "|", "||", ";", "then", "do")) or _basename(t) in BARE_FETCHERS:
                self.bad(node, "process_fetcher", f"a shell command starts {_basename(t)}")
                return
        if "://" in cmd:
            self.bad(node, "process_url", "a shell command carries a URL")

    # ---- strings
    def visit_Constant(self, node: ast.Constant) -> None:
        v = node.value
        if isinstance(v, str) and id(node) not in self.docstrings:
            self._string(node, v, True)

    def visit_JoinedStr(self, node: ast.JoinedStr) -> None:
        first = node.values[0] if node.values else None
        if self.allow and isinstance(first, ast.Constant) and isinstance(first.value, str) and "://" in first.value:
            h = host_of(first.value)
            second = ast.unparse(node.values[1].value) if len(node.values) > 1 and isinstance(node.values[1], ast.FormattedValue) else ""
            if not h and second in self.allow.loopback_names and re.fullmatch(r"[a-zA-Z][a-zA-Z0-9+.\-]*://", first.value):
                self.loopback_evidence = True
                self.used.append(f"{self.relpath}: URL host from {second}")
            elif not h or (h not in LOOPBACK_HOSTS and h not in self.allow.hosts):
                self.bad(node, "remote_url", "an f-string URL does not start with a loopback or allowed host literal")
            else:
                self._mark_host(h)
            for v in node.values[1:]:
                if isinstance(v, ast.FormattedValue):
                    self.visit(v)
            return
        if isinstance(first, ast.FormattedValue) and any(isinstance(v, ast.Constant) and isinstance(v.value, str) and v.value.startswith("/")
                                                          for v in node.values[1:2]):
            src_first = ast.unparse(first.value)
            helpers = self.allow.loopback_helpers if self.allow else frozenset()
            if any(h + "(" in src_first for h in helpers):
                self.loopback_evidence = True
                self.used.append(f"{self.relpath}: URL from {src_first}")
        pre, _ = self.fold(node)
        if pre and self.has_process:
            self._fetcher_string(node, pre)
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        if isinstance(node.op, ast.Add) and id(node) not in self._folded_binops:
            for sub in ast.walk(node):
                if isinstance(sub, ast.BinOp):
                    self._folded_binops.add(id(sub))
            pre, ok = self.fold(node)
            if pre:
                self._string(node, pre, ok)
        self.generic_visit(node)

    def _mark_host(self, h: str) -> None:
        if h in LOOPBACK_HOSTS:
            self.loopback_evidence = True
        if self.allow and h in self.allow.hosts:
            self.host_evidence.add(h)
            self.used.append(f"{self.relpath}: host {h}")

    def _fetcher_string(self, node: ast.AST, s: str) -> None:
        first = s.split()[0] if s.split() else ""
        if _basename(first) in BARE_FETCHERS and (len(s.split()) > 1 or s.strip() == first):
            self.bad(node, "process_fetcher", f"names {_basename(first)}, a program that moves data over a network")

    def _string(self, node: ast.AST, v: str, complete: bool) -> None:
        if self.has_process:
            self._fetcher_string(node, v)
        h = host_of(v)
        if self.policy.pure and h is not None:
            self.bad(node, "pure_compute_url", "a pure-compute layer has no reason to name a URL")
        if h is not None and "{" not in h:
            self._mark_host(h)
            if self.allow and h not in LOOPBACK_HOSTS and h not in self.allow.hosts:
                self.bad(node, "remote_url", f"a URL literal names the host {h}")
        elif self.allow and v in self.allow.hosts:
            self.host_evidence.add(v)
        if any(w in v for w in LOOPBACK_WORDS) and len(v) < 200:
            self.loopback_evidence = True

    # ---- after the walk
    def _finish(self) -> None:
        a = self.allow
        if not a or self.policy.pure or self.policy.kind == "runtime":
            return
        net_clients = {p for p in self.network_used}
        if not net_clients:
            return
        if a.hosts:
            if not (self.host_evidence & a.hosts):
                self.bad(1, "remote_not_demonstrated", f"allowed to reach {', '.join(sorted(a.hosts))} but the module carries no such host literal")
        elif not self.loopback_evidence:
            self.bad(1, "loopback_not_demonstrated",
                     "uses a network client but the module carries no literal 127.0.0.1 or localhost, no listed loopback constant and "
                     "no listed loopback helper, so it is not demonstrably loopback-only")


def analyse(src: str, relpath: str, policy: Policy, allow: Allow | None) -> tuple[list[Violation], list[str]]:
    a = Analyzer(src, relpath, policy, allow).run()
    return a.out, [u for u in a.used if u]


def allow_for(relpath: str, table: dict[str, Allow]) -> Allow | None:
    for pat, a in table.items():
        if fnmatch.fnmatch(relpath, pat):
            return a
    return None


__all__: list[Any] = ["Allow", "Policy", "Violation", "Analyzer", "analyse", "allow_for"]
