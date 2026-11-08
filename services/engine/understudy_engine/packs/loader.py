"""Role pack loader (ROL-1). A pack is a directory under ``packages/packs/<id>/`` with a ``pack.yaml``.

``load_pack`` returns a ``Pack`` that parses sub-files lazily (mapping, expert steps, routines, curriculum,
persona, priors, task config). ``plugin_refs`` are accepted and kept as data; nothing here calls them (ROL-5).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ..cogs.mapper import Mapping, compile_mapping, load_mapping
from ..store.paths import repo_root
from ..yamlcache import load_yaml_file


class PackError(Exception):
    def __init__(self, code: str, message: str, status: int = 404):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def packs_dir() -> Path:
    env = os.environ.get("UNDERSTUDY_PACKS_DIR")
    return Path(env).expanduser() if env else repo_root() / "packages" / "packs"


def pack_dirs(root: Path | None = None) -> list[Path]:
    root = root or packs_dir()
    if not root.exists():
        return []
    return sorted(d for d in root.iterdir() if d.is_dir() and (d / "pack.yaml").is_file())


def _read(path: Path) -> Any:
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    return load_yaml_file(path)                  # parsed once per version of the file (yamlcache.py)


@dataclass
class Pack:
    dir: Path
    data: dict
    warnings: list[str] = field(default_factory=list)
    _cache: dict = field(default_factory=dict, repr=False)

    # ---- identity
    @property
    def id(self) -> str:
        return self.data["id"]

    @property
    def name(self) -> str:
        return self.data["name"]

    @property
    def summary(self) -> str:
        return self.data.get("summary", "")

    @property
    def depth(self) -> str:
        return self.data.get("depth") or ("deep" if "tasks" in self.data else "thin")

    @property
    def plugin_refs(self) -> list:
        return list(self.data.get("plugin_refs") or [])

    def summary_row(self) -> dict:
        return {"id": self.id, "name": self.name, "summary": self.summary, "depth": self.depth}

    # ---- sub-files
    def file(self, key: str) -> Any:
        """Parsed content of the file a pack.yaml key points at (``routines``, ``curriculum``, ``persona``, ...)."""
        if key not in self._cache:
            rel = self.data.get(key)
            if rel is None:
                raise PackError("missing_key", f"Pack {self.id} has no {key!r}.", 404)
            path = self.dir / rel
            if not path.is_file():
                raise PackError("missing_file", f"Pack {self.id}: {key} points at {rel}, which does not exist.", 500)
            self._cache[key] = _read(path)
        return self._cache[key]

    def nested(self, section: str, key: str) -> Any:
        rel = (self.data.get(section) or {}).get(key)
        if rel is None:
            raise PackError("missing_key", f"Pack {self.id} has no {section}.{key}.", 404)
        cache_key = f"{section}.{key}"
        if cache_key not in self._cache:
            self._cache[cache_key] = _read(self.dir / rel)
        return self._cache[cache_key]

    @property
    def extra_cogs(self) -> list[str]:
        return list((self.data.get("cogs") or {}).get("extra") or [])

    def cog_mapping(self) -> Mapping:
        """The pack's cog mapping in the engine's rule format. If the pack's file is in another format, the
        built-in default is used and a warning is recorded (the contract is the rule format of default_mapping.yaml)."""
        if "mapping" not in self._cache:
            mapping: Mapping
            try:
                doc = self.nested("cogs", "mapping")
                mapping = compile_mapping(doc) if "rules" in doc else load_mapping(None)
                if "rules" not in doc:
                    self.warnings.append(f"{self.id}: cogs.mapping is not in the engine rule format; the default mapping is used")
            except (PackError, FileNotFoundError):
                mapping = load_mapping(None)
                self.warnings.append(f"{self.id}: no readable cogs.mapping; the default mapping is used")
            self._cache["mapping"] = mapping
        return self._cache["mapping"]

    def sensitive_fields(self) -> dict:
        return self.nested("risk_classes", "sensitive_fields")

    def risk_classes(self) -> dict:
        rc = self.data.get("risk_classes") or {}
        return {"irreversible": list(rc.get("irreversible") or []), "outward": list(rc.get("outward") or [])}

    def questions(self) -> list[dict]:
        return list((self.data.get("onboarding") or {}).get("questions") or [])

    def tone_defaults(self) -> dict:
        return dict(self.data.get("tone_defaults") or {})


def load_pack(pack_id: str, root: Path | None = None) -> Pack:
    root = root or packs_dir()
    d = root / pack_id
    if not (d / "pack.yaml").is_file():
        known = ", ".join(p.name for p in pack_dirs(root)) or "none"
        raise PackError("unknown_pack", f"No role pack {pack_id!r}. Known packs: {known}.")
    return Pack(d, _read(d / "pack.yaml"))


def load_all(root: Path | None = None) -> list[Pack]:
    return [Pack(d, _read(d / "pack.yaml")) for d in pack_dirs(root)]


def list_packs(root: Path | None = None) -> list[dict]:
    return [p.summary_row() for p in load_all(root)]
