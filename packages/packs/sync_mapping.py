#!/usr/bin/env python
"""Re-sync the packs' mapping.yaml rule copies with the engine default
(services/engine/understudy_engine/cogs/default_mapping.yaml).

    uv run python packages/packs/sync_mapping.py

The deep pack's `params` and `rules` become a verbatim copy of the default (a test enforces equality).
The thin packs keep their own role rules and params but take the default's base-cog rules, copied verbatim
(minus any rule that produces one of the benefits pack's role cogs).
Everything else in each file (zones, capture_sites, examples, comments) is left alone.
"""
from __future__ import annotations

import re
import sys

import yaml
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT = HERE.parents[1] / "services" / "engine" / "understudy_engine" / "cogs" / "default_mapping.yaml"
BASE_MARK = "  # ---- base cogs\n"


def _block(text: str, start: str, end_pat: str) -> tuple[int, int]:
    i = text.index(start)
    m = re.search(end_pat, text[i:], re.M)
    return i, (i + m.start() if m else len(text))


def main() -> int:
    default = DEFAULT.read_text()
    d_params = default[default.index("params:\n"):default.index("extra_cogs:")]
    d_rules = default[default.index("rules:\n"):]
    d_base = d_rules[d_rules.index(BASE_MARK):]
    # a role rule that sits among the base rules (the default keeps nav + calc_result -> READ_RESULT there) is not
    # a base rule: thin packs get only the lines whose cog is not one of the default pack's extra cogs
    extra = yaml.safe_load(default)["extra_cogs"]
    d_base = "".join(line for line in d_base.splitlines(keepends=True)
                     if not any(f"cog: {c}" in line for c in extra))

    ben = HERE / "benefits-processor" / "mapping.yaml"
    t = ben.read_text()
    i, j = _block(t, "params:\n", r"^extra_cogs:")
    t = t[:i] + d_params + t[j:]
    i, j = _block(t, "rules:\n", r"^examples:")
    t = t[:i] + d_rules.rstrip("\n") + "\n\n" + t[j:]
    ben.write_text(t)

    for pack in ("data-analyst", "programmer"):
        f = HERE / pack / "mapping.yaml"
        t = f.read_text()
        i, j = _block(t, BASE_MARK, r"^capture_sites:")
        t = t[:i] + d_base.rstrip("\n") + "\n\n" + t[j:]
        f.write_text(t)
        print("synced base rules of", pack)
    print("synced", ben.relative_to(HERE.parents[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
