"""``understudy pack validate``."""
from __future__ import annotations

from pathlib import Path

from .loader import pack_dirs
from .validate import validate_pack


def validate_command(paths: list[str] | None = None) -> int:
    dirs = [Path(p) for p in paths] if paths else pack_dirs()
    if not dirs:
        print("FAIL  no packs found (looked in packages/packs)")
        return 1
    failed = False
    for d in dirs:
        errs = validate_pack(d)
        if errs:
            failed = True
            print(f"FAIL  pack {d.name}")
            for e in errs:
                print(f"      {e}")
        else:
            print(f"ok    pack {d.name}")
    return 1 if failed else 0
