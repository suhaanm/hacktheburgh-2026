#!/usr/bin/env python
"""Regenerate the dashboard's example connections fixture from the real engine view (CONNECTIONS).

    uv run python scripts/gen_connections_fixture.py

It writes apps/dashboard/src/screens/Connections/fixture.json: every curated preset, every one OFF, with the consent lines the engine would show. The
dashboard falls back to it only when the engine is not running, and says so. It reads a throwaway data folder, never the real one, and no token,
account or network is involved.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    tmp = tempfile.mkdtemp(prefix="knack-fixture-")
    os.environ["UNDERSTUDY_DATA_DIR"] = str(Path(tmp) / "data")
    os.environ["UNDERSTUDY_HOME"] = str(Path(tmp) / "home")
    from understudy_engine.connections import registry, service

    rows = service.listing()
    out = ROOT / "apps" / "dashboard" / "src" / "screens" / "Connections" / "fixture.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = {"meta": {"origin": "synthetic", "n": len(rows), "n_unit": "connections", "split": None, "interval_level": 0.95,
                    "note": "Example connections.", "generated_at": None},
           "roles": registry.role_lists(), "data": rows}
    out.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} presets to {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
