"""Synthetic L1 recordings of an expert session on a sandbox site (what the extension would send for a routine the
worker opted in). Shape: packages/schema/recording.schema.json. Slots are named after the page's own field names;
no values, ever. Used by the compile step's tests and the demo."""
from __future__ import annotations

import re
from typing import Any

from .bundles import SELECT_PARAMS
from .specs import SITES, site_base_urls


def slot_name(field_key: str) -> str:
    s = re.sub(r"[^a-z0-9_]", "_", field_key.lower())
    return (s if re.match(r"[a-z]", s) else "f_" + s)[:31]


def synthetic_recording(site: str, layout: str = "v1", *, routine_id: str = "calc-entry-3x",
                        base_urls: dict[str, str] | None = None, recording_id: str = "rec_0a1b2c3d4e5f",
                        with_cliff: bool = True, by_role: tuple[str, ...] = (), person: str = "p_demo",
                        skip_sensitive: bool = True) -> dict[str, Any]:
    """`by_role` lists canonical params to record by role and accessible name instead of by selector.
    `skip_sensitive` mimics the extension: the health-related "limited capability" field matches the sensitive-field
    list, so the recorder never captures it (it is only counted in `skipped_sensitive`)."""
    spec = SITES[site]
    urls = base_urls or site_base_urls()
    steps: list[dict[str, Any]] = [{"op": "goto", "t_ms": 0,
                                    "url": urls[site] + spec.start_path + ("?layout=v2" if layout == "v2" else "")}]
    t = 1500
    labels = _labels(site)
    skipped = 0
    for i, params in enumerate(spec.steps):
        for p in params:
            if skip_sensitive and p == "limited_capability":
                skipped += 1
                continue
            op = "select" if p in SELECT_PARAMS else "fill"
            st: dict[str, Any] = {"op": op, "t_ms": t, "param": slot_name(spec.fields(layout)[p])}
            if p in by_role:
                role = "combobox" if op == "select" else ("spinbutton" if p in ("adult1_age", "adult2_age") else "textbox")
                st.update({"role": role, "name": labels[p]})
            else:
                st["selector"] = spec.selector(p, layout)
            if op == "fill":
                st["input_type"] = "text"
            steps.append(st)
            t += 2300
        steps.append({"op": "click", "t_ms": t, "selector": spec.buttons(layout)[i]})
        t += 1800
    if with_cliff:
        steps.append({"op": "click", "t_ms": t, "selector": "#cliff-btn"})
    return {"schema": 1, "routine_id": routine_id, "recording_id": recording_id, "role": "benefits-processor",
            "person": person, "skipped_sensitive": skipped, "steps": steps}


def _labels(site: str) -> dict[str, str]:
    from .sites import _a_labels

    if site == "a":
        return {k: v[0] for k, v in _a_labels().items()}
    return {p: p.replace("_", " ") for p in SITES[site].fields_v1}
