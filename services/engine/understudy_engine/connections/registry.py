"""The curated list of connection presets, and which role offers which (CONNECTIONS).

Presets come from the plugin framework: ``packages/connections/presets/*.yaml`` (kind mcp) and the source plugins that carry a ``connection``
block (the Graph calendar sources). The list is CURATED ONLY: there is no function here, and no route, that adds an arbitrary server. A
role offers presets through the ``connections:`` list at the end of its ``packages/packs/<role>/pack.yaml``.
"""
from __future__ import annotations

from typing import Any

import yaml

from ..plugins.loader import discover, manifest_paths
from ..plugins.manifest import check_manifest
from ..yamlcache import load_yaml_file
from .manifest import Preset
from .paths import packs_dir


def all_presets() -> dict[str, Preset]:
    """Every valid preset by id (a manifest with a problem is skipped here; ``problems()`` reports it)."""
    out: dict[str, Preset] = {}
    for pid, m in discover().items():
        if m.connection:
            out[pid] = Preset.from_manifest(m)
    return out


def get(preset_id: str) -> Preset | None:
    return all_presets().get(preset_id)


def role_lists() -> dict[str, list[str]]:
    """``{role id: [preset id, ...]}`` from every pack's ``connections:`` list, in the order the pack gives."""
    out: dict[str, list[str]] = {}
    base = packs_dir()
    if not base.is_dir():
        return out
    for d in sorted(p for p in base.iterdir() if (p / "pack.yaml").is_file()):
        try:
            data = load_yaml_file(d / "pack.yaml") or {}
        except (OSError, yaml.YAMLError):
            continue
        ids = data.get("connections")
        if isinstance(ids, list):
            out[str(data.get("id", d.name))] = [str(i) for i in ids]
    return out


def for_role(role: str) -> list[Preset]:
    presets = all_presets()
    return [presets[i] for i in role_lists().get(role, []) if i in presets]


def roles_for(preset_id: str) -> list[str]:
    return [r for r, ids in role_lists().items() if preset_id in ids]


def problems() -> list[str]:
    """Everything wrong with the curated list: invalid manifests, a pack that names a preset that does not exist, a preset no pack offers."""
    out: list[str] = []
    for p in manifest_paths():
        try:
            data: Any = load_yaml_file(p)
        except (OSError, yaml.YAMLError):
            out.append(f"{p.name}: cannot read")
            continue
        if isinstance(data, dict) and data.get("connection") is not None:
            out.extend(f"{data.get('id', p.name)}: {x}" for x in check_manifest(data))
    known = all_presets()
    listed: set[str] = set()
    for role, ids in role_lists().items():
        for i in ids:
            listed.add(i)
            if i not in known:
                out.append(f"pack {role}: connections lists {i!r}, which is not a preset")
        if len(set(ids)) != len(ids):
            out.append(f"pack {role}: connections repeats an id")
    for pid in known:
        if pid not in listed:
            out.append(f"{pid}: no role pack offers this preset")
    return out
