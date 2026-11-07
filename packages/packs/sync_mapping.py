#!/usr/bin/env python
"""Re-sync the packs' mapping.yaml rule copies with the engine default
(services/engine/understudy_engine/cogs/default_mapping.yaml).

    uv run python packages/packs/sync_mapping.py

The deep pack's `params` and `rules` become a verbatim copy of the default (a test enforces equality).
The thin packs keep their own role rules and params but take the default's base-cog rules, copied verbatim.
Everything else in each file (zones, capture_sites, examples, comments) is left alone.
"""
from __future__ import annotations

import re
import sys
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
