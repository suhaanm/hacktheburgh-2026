"""Discover, validate and instantiate source plugins.

Manifests come from the bundled ``builtin/<id>/plugin.yaml``, from directories in ``UNDERSTUDY_PLUGIN_PATH`` (os.pathsep
separated; each child directory holding a ``plugin.yaml``), and from ``register_manifest`` (another track registers its own
manifest, for example the git adapter). Graph sources are registered but **disabled** until ``UNDERSTUDY_GRAPH=1``.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .base import Source
from .manifest import ManifestError, PluginManifest, check_manifest, load_manifest, resolve_entry

BUILTIN_DIR = Path(__file__).resolve().parent / "builtin"
_REGISTERED: dict[str, PluginManifest] = {}


class PluginDisabled(Exception):
    pass


def register_manifest(manifest: str | Path | dict[str, Any]) -> PluginManifest:
    """Register a manifest (a ``plugin.yaml`` path, its directory, or a dict). Validated now; raises ``ManifestError``."""
    if isinstance(manifest, dict):
        problems = check_manifest(manifest)
        if problems:
            raise ManifestError(str(manifest.get("id", "(dict)")), problems)
        m = PluginManifest.from_dict(manifest)
    else:
        m = load_manifest(manifest)
    _REGISTERED[m.id] = m
    return m


def unregister(plugin_id: str) -> None:
    _REGISTERED.pop(plugin_id, None)


def _dirs() -> list[Path]:
    dirs = [BUILTIN_DIR]
    for part in os.environ.get("UNDERSTUDY_PLUGIN_PATH", "").split(os.pathsep):
        if part.strip():
            dirs.append(Path(part.strip()).expanduser())
    return dirs


def manifest_paths() -> list[Path]:
    out: list[Path] = []
    for d in _dirs():
        if not d.is_dir():
            continue
        if (d / "plugin.yaml").is_file():
            out.append(d / "plugin.yaml")
        out.extend(sorted(p / "plugin.yaml" for p in d.iterdir() if (p / "plugin.yaml").is_file()))
    return out


@dataclass(frozen=True)
class ValidationResult:
    path: str
    id: str | None
    ok: bool
    problems: tuple[str, ...] = ()
    enabled: bool | None = None


def is_enabled(m: PluginManifest) -> bool:
    if m.enable_flag and os.environ.get(m.enable_flag, "").strip().lower() in ("1", "true", "yes"):
        return True
    if m.network or m.requires_token:
        return False
    return m.default_enabled


def validate_paths(paths: list[Path] | None = None) -> list[ValidationResult]:
    """Validate manifests (default: every discoverable and registered one). Never raises."""
    results: list[ValidationResult] = []
    targets = [Path(p) for p in paths] if paths else manifest_paths()
    for p in targets:
        pp = p / "plugin.yaml" if p.is_dir() else p
        try:
            data = yaml.safe_load(pp.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            results.append(ValidationResult(str(pp), None, False, (f"cannot read manifest ({type(exc).__name__})",)))
            continue
        problems = check_manifest(data)
        pid = data.get("id") if isinstance(data, dict) else None
        enabled = None
        if not problems:
            enabled = is_enabled(PluginManifest.from_dict(data, str(pp)))
        results.append(ValidationResult(str(pp), pid, not problems, tuple(problems), enabled))
    if not paths:
        for m in _REGISTERED.values():
            if not any(r.id == m.id for r in results):
                problems = check_manifest({"id": m.id, "version": m.version, "kind": m.kind, "description": m.description,
                                           "permissions": list(m.permissions), "egress": m.egress, "entry": m.entry,
                                           **({"schema": m.schema} if m.schema else {}),
                                           "default_enabled": m.default_enabled, "network": m.network,
                                           "requires_token": m.requires_token,
                                           **({"enable_flag": m.enable_flag} if m.enable_flag else {})})
                results.append(ValidationResult(m.path or "(registered)", m.id, not problems, tuple(problems), is_enabled(m)))
    return results


def discover() -> dict[str, PluginManifest]:
    """Valid manifests by id (invalid ones are skipped here; ``validate_paths`` reports them)."""
    found: dict[str, PluginManifest] = {}
    for p in manifest_paths():
        try:
            m = load_manifest(p)
        except ManifestError:
            continue
        found[m.id] = m
    found.update(_REGISTERED)
    return found


def load_source_class(plugin_id: str) -> type[Source]:
    m = discover().get(plugin_id)
    if m is None:
        raise KeyError(f"no plugin with id {plugin_id!r}")
    if not is_enabled(m):
        raise PluginDisabled(f"plugin {plugin_id!r} is off" + (f" (set {m.enable_flag}=1)" if m.enable_flag else ""))
    return resolve_entry(m.entry)


def load_source(plugin_id: str, **kwargs: Any) -> Source:
    """Instantiate an enabled source plugin by id. Graph sources need ``token_provider`` (and stay off without the flag)."""
    return load_source_class(plugin_id)(**kwargs)
