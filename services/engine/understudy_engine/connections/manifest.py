"""The connection block of a plugin manifest: validation, the typed ``Preset`` view, the command hash and the consent lines (CONNECTIONS).

A preset is a plugin manifest (``kind: mcp``, or a source plugin that carries a ``connection`` block) plus a ``connection`` block that
``packages/schema/connection.schema.json`` describes. Nothing in it is trusted from the server it names. The things that matter:

* ``tools.classes`` is OUR table of the tools we know; the agent's classifier (``understudy_agent.connections.classify``) uses it first.
* ``command_hash`` pins what would run: the launcher, the arguments, the pinned version, the hosts and the names of the credential
  variables, or, for a stand-in, the SHA-256 of the stand-in script. A stored consent carries the hash it was given for; when the manifest
  (or the script) changes, the hash differs and the connection is disabled until the worker confirms again.
* ``consent`` words what the worker is agreeing to: the publisher, the package and its pinned version, the hosts, and "with your token".
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator

from .paths import repo_root

CLASS_NAMES = ("read", "write", "send", "destructive", "execute")
MODES = ("example", "real")
LAUNCHERS = ("npx", "uvx", "docker")
_PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_]{1,30})\}")
_SAFE_BUILTIN_PLACEHOLDERS = frozenset({"sandbox", "synthetic"})
_SHELL_META = re.compile(r"[;&|`$<>\\\n\r]")
_REGISTRY_LABEL = {"npm": "npm", "pypi": "PyPI", "oci": "container image", "release": "release", "plugin": "built in"}


# --------------------------------------------------------------------------------------------------------- validation
@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    path = repo_root() / "packages" / "schema" / "connection.schema.json"
    return Draft202012Validator(json.loads(path.read_text(encoding="utf-8")))


def _fmt(e: Any) -> str:
    where = ".".join(str(p) for p in e.absolute_path) or "(connection)"
    msg = e.message if len(e.message) < 160 else e.message[:157] + "..."
    return f"connection.{where}: {msg}"


def connection_problems(data: dict[str, Any]) -> list[str]:
    """Every problem with the ``connection`` block of a manifest dict: the JSON Schema first, then the rules a schema cannot state. Never
    echoes a value that came from a free-text field beyond a short schema message."""
    block = data.get("connection")
    if not isinstance(block, dict):
        return ["connection: missing or not a mapping"]
    problems = [_fmt(e) for e in sorted(_validator().iter_errors(block), key=lambda e: list(map(str, e.absolute_path)))]
    if problems:
        return problems
    kind = data.get("kind")
    real = block.get("real")
    standin = block["standin"]

    # stand-in: a server of ours or an existing source plugin, never both, never neither
    if ("script" in standin) == ("source" in standin):
        problems.append("connection.standin: give exactly one of script or source")
    if "script" in standin and not (repo_root() / standin["script"]).is_file():
        problems.append(f"connection.standin.script: {standin['script']} does not exist")
    declared = {p["name"] for p in (real or {}).get("params", [])}
    for a in standin.get("args", []):
        for ph in _PLACEHOLDER.findall(a):
            if ph not in _SAFE_BUILTIN_PLACEHOLDERS:
                problems.append(f"connection.standin.args: unknown placeholder {{{ph}}}")

    # tool table: a tool is in one class only, and an SQL classifier names a tool that exists
    seen: dict[str, str] = {}
    for cls, names in block["tools"]["classes"].items():
        for n in names:
            if n in seen:
                problems.append(f"connection.tools.classes: {n!r} is listed as both {seen[n]} and {cls}")
            seen[n] = cls
    for n in block["tools"].get("classifiers", {}):
        if n not in seen:
            problems.append(f"connection.tools.classifiers: {n!r} is not in the class table")

    if real is None:
        return problems
    transport = real["transport"]
    if kind == "mcp" and transport == "plugin":
        problems.append("connection.real.transport: plugin is for a source preset, not kind mcp")
    if kind == "source" and transport != "plugin":
        problems.append("connection.real.transport: a source preset must use transport plugin")
    cred_envs = [c["env"] for c in real.get("credentials", [])]
    if len(set(cred_envs)) != len(cred_envs):
        problems.append("connection.real.credentials: an environment name is repeated")
    clash = set(cred_envs) & set(real.get("env_fixed", {}))
    if clash:
        problems.append(f"connection.real.env_fixed: {sorted(clash)[0]} is also a credential")
    for name in real.get("env_fixed", {}):
        if re.search(r"TOKEN|SECRET|PASSWORD|KEY", name):
            problems.append(f"connection.real.env_fixed: {name} looks like a secret; a secret is entered by the worker only")
    for p in real.get("params", []):
        if p.get("env") and p["env"] in cred_envs:
            problems.append(f"connection.real.params: {p['name']} reuses a credential variable")

    if transport == "stdio":
        args = real["args"]
        version = real["version"]
        if not any(version in a for a in args):
            problems.append(f"connection.real.args: the pinned version {version} must appear in the arguments")
        for a in args:
            if re.search(r"@latest|:latest\b|==latest|@\*|@\^|@~", a):
                problems.append("connection.real.args: a floating version is not allowed; pin an exact one")
            bare = _PLACEHOLDER.sub("", a)
            if _SHELL_META.search(bare):
                problems.append("connection.real.args: an argument has a shell character; no shell is ever used")
            for ph in _PLACEHOLDER.findall(a):
                if ph not in declared:
                    problems.append(f"connection.real.args: placeholder {{{ph}}} is not a declared param")
        launcher = real["command"]
        if launcher == "npx" and not (args and args[0] == "-y"):
            problems.append("connection.real.args: an npx launch starts with -y so it never waits on a prompt")
        if launcher == "docker" and not (args[:3] == ["run", "-i", "--rm"] and any(a.endswith(":" + version) for a in args)):
            problems.append("connection.real.args: a docker launch is 'run -i --rm ... image:<pinned version>'")
        if launcher == "docker" and any(a in ("-v", "--volume", "--privileged", "--network", "--net", "-p", "--publish") for a in args):
            problems.append("connection.real.args: a docker launch mounts, publishes or networks nothing beyond the default")
    for h in real.get("hosts", []):
        if h.startswith("{") and h[1:-1] not in declared:
            problems.append(f"connection.real.hosts: placeholder {h} is not a declared param")
    if real.get("url") and not real["url"].startswith("https://"):
        problems.append("connection.real.url: https only")
    if not any("LICENSE" in s.upper() for s in real["sources"]) and transport != "plugin":
        problems.append("connection.real.sources: a LICENSE file URL must be among the sources")
    return problems


# --------------------------------------------------------------------------------------------------------- typed view
@dataclass(frozen=True)
class ToolTable:
    """OUR classification of a server's tools. ``lookup`` returns the class of a known tool or None."""

    classes: dict[str, str]                       # tool name -> class
    classifiers: dict[str, str] = field(default_factory=dict)
    unlisted: str = "verbs"                       # verbs | refuse

    def lookup(self, name: str) -> str | None:
        return self.classes.get(name)

    def names(self, cls: str) -> list[str]:
        return sorted(n for n, c in self.classes.items() if c == cls)

    def counts(self) -> dict[str, int]:
        out = {c: 0 for c in CLASS_NAMES}
        for c in self.classes.values():
            out[c] += 1
        return out


@dataclass(frozen=True)
class Preset:
    id: str
    app: str
    group: str
    kind: str                                     # mcp | source | tool
    version: str
    description: str
    reads: str
    caution: str
    standin: dict[str, Any]
    real: dict[str, Any] | None
    tools: ToolTable
    limitations: tuple[str, ...] = ()
    path: str | None = None
    short: str = ""                 # what it reads in at most six words, for a row of the list

    # ---- what is available
    @property
    def has_real(self) -> bool:
        return self.real is not None

    @property
    def transport(self) -> str:
        return (self.real or {}).get("transport", "stdio")

    @property
    def credential_envs(self) -> list[str]:
        return [c["env"] for c in (self.real or {}).get("credentials", [])]

    @property
    def params(self) -> list[dict[str, Any]]:
        return list((self.real or {}).get("params", []))

    def hosts(self, params: dict[str, str] | None = None) -> list[str]:
        """The hosts the real server's own process connects to; ``{param}`` entries resolve to the host of the worker's address."""
        out: list[str] = []
        for h in (self.real or {}).get("hosts", []):
            if h.startswith("{"):
                raw = (params or {}).get(h[1:-1], "")
                host = urlsplit(raw if "://" in raw else "//" + raw).hostname if raw else None
                out.append(host or "your own address")
            else:
                out.append(h)
        return out

    @classmethod
    def from_manifest(cls, m: Any) -> "Preset":
        c = m.connection
        if not isinstance(c, dict):
            raise ValueError(f"{m.id}: no connection block")
        classes = {n: k for k, names in c["tools"]["classes"].items() for n in names}
        return cls(id=m.id, app=c["app"], group=c["group"], kind=m.kind, version=m.version, description=m.description, reads=c["reads"],
                   caution=c.get("caution", ""), standin=dict(c["standin"]), real=dict(c["real"]) if c.get("real") else None,
                   tools=ToolTable(classes, dict(c["tools"].get("classifiers", {})), c["tools"].get("unlisted", "verbs")),
                   limitations=tuple(c.get("limitations", ())), path=m.path, short=c.get("short", ""))


# --------------------------------------------------------------------------------------------------------- the hash
def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def standin_script_sha(preset: Preset) -> str | None:
    """SHA-256 over EVERY file of the stand-in folder (scripts and fixtures): a stand-in is a family of files, and a change to any of them
    changes what runs, so every example connection must be confirmed again. None for a preset whose stand-in is an existing source plugin."""
    if not preset.standin.get("script"):
        return None
    base = repo_root() / "packages" / "connections" / "standins"
    h = hashlib.sha256()
    try:
        for p in sorted(base.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts and p.suffix in (".py", ".json"):
                h.update(str(p.relative_to(base)).encode())
                h.update(p.read_bytes())
    except OSError:
        return None
    return h.hexdigest()


def command_hash(preset: Preset, mode: str) -> str:
    """What would run, as a short hash. A stored consent keeps the hash it was given for; a different hash means the connection is off
    until the worker confirms again. For a stand-in the stand-in script's own content is part of it. Worker-chosen values (a folder, a
    site address) and tokens are NOT part of it: they are the worker's inputs, not the code."""
    if mode == "example":
        body: dict[str, Any] = {"mode": "example", "script": preset.standin.get("script"), "script_sha256": standin_script_sha(preset),
                                "args": preset.standin.get("args", []), "source": preset.standin.get("source")}
    elif preset.real is None:
        raise ValueError(f"{preset.id} has no real mode")
    else:
        r = preset.real
        body = {"mode": "real", "transport": r["transport"], "command": r.get("command"), "args": r.get("args", []), "registry": r.get("registry"),
                "package": r.get("package"), "version": r.get("version"), "url": r.get("url"), "env_fixed": r.get("env_fixed", {}),
                "hosts": r.get("hosts", []), "credential_envs": preset.credential_envs,
                "param_envs": {p["name"]: p.get("env") for p in r.get("params", [])}}
    return "sha256:" + hashlib.sha256(_canon(body).encode("ascii")).hexdigest()[:24]


# --------------------------------------------------------------------------------------------------------- the words
def _reads_line(preset: Preset) -> str:
    r = preset.reads.strip().rstrip(".")
    return f"Reads {r[0].lower() + r[1:]}."


def consent(preset: Preset, mode: str, params: dict[str, str] | None = None) -> dict[str, Any]:
    """What the worker is agreeing to, in plain words: ``summary`` (the sentences joined), ``lines`` (the same, short, for the chip) and the facts
    behind it. For a real connection it names the publisher, the package, the pinned version, the hosts, and says "with your token"."""
    if mode not in MODES:
        raise ValueError("mode must be example or real")
    if mode == "example":
        lines = ["Runs on this Mac.", _reads_line(preset), "No account is used and nothing leaves this Mac.",
                 "Any change needs your click. Revoke any time."]
        return {"mode": mode, "summary": " ".join(lines), "lines": lines, "example": True, "publisher": "Knack", "package": preset.standin.get("script") or
                preset.standin.get("source"), "version": preset.version, "hosts": [], "needs_token": False, "caution": ""}
    if preset.real is None:
        raise ValueError(f"{preset.id} has no real mode")
    r = preset.real
    hosts = preset.hosts(params)
    pkg = f"{_REGISTRY_LABEL[r.get('registry', 'plugin')]} {r['package']}" if r.get("package") else ""
    needs_token = bool(preset.credential_envs)
    if r["transport"] == "plugin":
        start = f"Knack's own read-only {preset.app} reader ({r['package']} {r['version']}) reads it through Microsoft Graph"
    else:
        start = f"Knack starts {preset.app} server {r['version']} ({pkg}) by {r['publisher']}"
    if hosts:
        reach = f"It talks to {', '.join(hosts)} " + ("with your token." if needs_token else "with your own sign-in on this Mac.")
    else:
        reach = "It stays on this Mac."
    lines = [f"{start}.", reach, _reads_line(preset) + " Any change needs your click.", "Revoke any time."]
    if preset.caution:
        lines.insert(2, f"{preset.caution}.")
    return {"mode": mode, "summary": " ".join(lines), "lines": lines, "example": False, "publisher": r["publisher"], "publisher_kind": r["publisher_kind"],
            "package": r.get("package"), "version": r.get("version"), "registry": r.get("registry"), "license": r["license"], "hosts": hosts,
            "needs_token": needs_token, "caution": preset.caution}


def load_preset_file(path: str | Path) -> Preset:
    """Load one preset YAML through the plugin framework's validator (raises ``ManifestError`` listing every problem)."""
    from ..plugins.manifest import load_manifest

    return Preset.from_manifest(load_manifest(path))
