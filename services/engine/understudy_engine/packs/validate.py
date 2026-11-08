"""Pack validation (ROL-1): schema checks here, plus the platform's cross-file checks when its validator is present."""
from __future__ import annotations

import importlib.util
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from ..store.paths import repo_root
from .loader import pack_dirs, packs_dir

# pack.yaml key -> $defs name in pack.schema.json for the file it points at
SUBFILES = {
    ("cogs", "mapping"): "mapping",
    ("expert_policy", "steps"): "expert_steps",
    ("risk_classes", "sensitive_fields"): "sensitive_fields",
    ("routines",): "routine_templates",
    ("curriculum",): "curriculum",
    ("persona",): "persona",
    ("priors",): "priors",
    ("habits",): "habits",          # RD: optional; the loop below skips a pack that does not name one
}


@lru_cache(maxsize=1)
def pack_schema() -> dict:
    return json.loads((repo_root() / "packages" / "schema" / "pack.schema.json").read_text())


def _def_validator(name: str) -> Draft202012Validator:
    return Draft202012Validator({"$ref": f"#/$defs/{name}", "$defs": pack_schema()["$defs"]})


def _errors(validator: Draft202012Validator, data: Any, where: str) -> list[str]:
    out = []
    for err in sorted(validator.iter_errors(data), key=lambda e: list(map(str, e.absolute_path))):
        path = "/".join(str(p) for p in err.absolute_path) or "(root)"
        out.append(f"{where}: {path}: {err.message[:240]}")
    return out


def _read(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    return json.loads(text) if path.suffix == ".json" else yaml.safe_load(text)


def schema_errors(pack_dir: Path) -> list[str]:
    """pack.yaml against pack.schema.json, then each sub-file against its $defs schema. Errors are plain strings."""
    pack_dir = Path(pack_dir)
    name = pack_dir.name
    if not (pack_dir / "pack.yaml").is_file():
        return [f"{name}: pack.yaml is missing"]
    try:
        pack = _read(pack_dir / "pack.yaml")
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        return [f"{name}/pack.yaml: does not parse: {str(exc).splitlines()[0]}"]
    errs = _errors(Draft202012Validator(pack_schema()), pack, f"{name}/pack.yaml")
    if errs:
        return errs
    if pack["id"] != name:
        errs.append(f"{name}/pack.yaml: id {pack['id']!r} must equal the directory name")
    for keys, def_name in SUBFILES.items():
        node: Any = pack
        for k in keys:
            node = node.get(k) if isinstance(node, dict) else None
        if node is None:
            continue
        path = pack_dir / node
        label = f"{name}/{node}"
        if not path.is_file():
            errs.append(f"{label}: referenced by pack.yaml but missing")
            continue
        try:
            doc = _read(path)
        except (yaml.YAMLError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            errs.append(f"{label}: does not parse: {str(exc).splitlines()[0]}")
            continue
        errs += _errors(_def_validator(def_name), doc, label)
    return errs


@lru_cache(maxsize=1)
def _platform_validator():
    path = repo_root() / "packages" / "packs" / "validate.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("understudy_platform_pack_validate", path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    except Exception:  # pragma: no cover - a broken platform validator must not break ours
        return None
    return mod


def validate_pack(pack_dir: Path | str, extended: bool = True) -> list[str]:
    """Errors for one pack (empty list = valid). ``extended`` adds the platform's cross-file checks if present."""
    pack_dir = Path(pack_dir)
    errs = schema_errors(pack_dir)
    if extended and not errs:
        mod = _platform_validator()
        if mod is not None:
            for e in mod.validate_pack(pack_dir):
                if e not in errs:
                    errs.append(e)
    return errs


def validate_all(root: Path | None = None, extended: bool = True) -> dict[str, list[str]]:
    return {d.name: validate_pack(d, extended) for d in pack_dirs(root or packs_dir())}
