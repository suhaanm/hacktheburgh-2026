"""Plugin manifest: load ``plugin.yaml``, validate it against ``packages/schema/plugin.schema.json`` and the loader's own
rules (the entry imports, is a ``Source`` subclass whose ``plugin_id`` equals the manifest id, the item schema exists)."""
from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from ..store.paths import schema_dir
from .base import Source
from .schemas import get_schema


@dataclass(frozen=True)
class PluginManifest:
    id: str
    version: str
    kind: str
    description: str
    permissions: tuple[str, ...]
    egress: str
    entry: str
    schema: str | None = None
    default_enabled: bool = True
    network: bool = False
    requires_token: bool = False
    enable_flag: str | None = None
    limitations: tuple[str, ...] = ()
    path: str | None = field(default=None, compare=False)
    connection: dict[str, Any] | None = field(default=None, compare=False)   # kind mcp / tool / a source preset (CONNECTIONS)

    @classmethod
    def from_dict(cls, d: dict[str, Any], path: str | None = None) -> "PluginManifest":
        return cls(id=d["id"], version=d["version"], kind=d["kind"], description=d["description"],
                   permissions=tuple(d["permissions"]), egress=d["egress"], entry=d.get("entry", ""), schema=d.get("schema"),
                   default_enabled=d.get("default_enabled", True), network=d.get("network", False),
                   requires_token=d.get("requires_token", False), enable_flag=d.get("enable_flag"),
                   limitations=tuple(d.get("limitations", ())), path=path, connection=d.get("connection"))


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    schema = json.loads((schema_dir() / "plugin.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def schema_errors(data: Any) -> list[str]:
    """JSON Schema problems, each as ``path: message`` (values of free-text fields are never echoed)."""
    out = []
    for e in sorted(_validator().iter_errors(data), key=lambda e: list(e.absolute_path)):
        where = ".".join(str(p) for p in e.absolute_path) or "(manifest)"
        msg = e.message if len(e.message) < 160 else e.message[:157] + "..."
        out.append(f"{where}: {msg}")
    return out


def resolve_entry(entry: str) -> type:
    """``module.path:ClassName`` to the class (raises ImportError / AttributeError / TypeError with a plain message)."""
    mod, _, name = entry.partition(":")
    cls = getattr(importlib.import_module(mod), name)
    if not (isinstance(cls, type) and issubclass(cls, Source)):
        raise TypeError(f"{entry} is not a Source subclass")
    return cls


def resolve_tool_entry(entry: str) -> Any:
    """``module.path:function`` to the callable of a ``kind: tool`` plugin (same plain-message errors as ``resolve_entry``)."""
    mod, _, name = entry.partition(":")
    fn = getattr(importlib.import_module(mod), name)
    if not callable(fn):
        raise TypeError(f"{entry} is not callable")
    return fn


def check_manifest(data: Any, *, check_entry: bool = True) -> list[str]:
    """All problems with a manifest dict: schema first, then entry, id and item-schema consistency."""
    problems = schema_errors(data)
    if problems or not isinstance(data, dict):
        return problems or ["(manifest): not a mapping"]
    if data["kind"] == "source" and get_schema(data.get("schema", "")) is None:
        problems.append(f"schema: {data.get('schema')!r} is not a registered item schema")
    if data["kind"] == "mcp" and "entry" in data:
        problems.append("entry: a kind mcp manifest has no entry; nothing of ours is imported for it")
    if check_entry and data["kind"] == "tool":
        try:
            resolve_tool_entry(data["entry"])
        except Exception as exc:                # noqa: BLE001 - any import failure is a validation failure
            problems.append(f"entry: cannot load {data['entry']} ({type(exc).__name__}: {exc})")
    elif check_entry and data["kind"] != "mcp":
        try:
            cls = resolve_entry(data["entry"])
        except Exception as exc:                # noqa: BLE001 - any import failure is a validation failure
            problems.append(f"entry: cannot load {data['entry']} ({type(exc).__name__}: {exc})")
        else:
            if cls.plugin_id != data["id"]:
                problems.append(f"entry: class plugin_id {cls.plugin_id!r} does not match manifest id {data['id']!r}")
            if data["kind"] == "source" and cls.schema_id != data.get("schema"):
                problems.append(f"entry: class schema_id {cls.schema_id!r} does not match manifest schema {data.get('schema')!r}")
    if "connection" in data:
        from ..connections.manifest import connection_problems       # lazy: the connections layer imports this module

        problems.extend(connection_problems(data))
    return problems


def load_manifest(path: str | Path, *, check_entry: bool = True) -> PluginManifest:
    """Load and validate one ``plugin.yaml``. Raises ``ManifestError`` listing every problem."""
    p = Path(path)
    if p.is_dir():
        p = p / "plugin.yaml"
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ManifestError(str(p), [f"cannot read manifest ({type(exc).__name__})"]) from None
    problems = check_manifest(data, check_entry=check_entry)
    if problems:
        raise ManifestError(str(p), problems)
    return PluginManifest.from_dict(data, str(p))


class ManifestError(ValueError):
    def __init__(self, path: str, problems: list[str]):
        super().__init__(f"{path}: " + "; ".join(problems))
        self.path, self.problems = path, problems
