"""What the routes return: one view of a preset for the dashboard (CONNECTIONS). Plain data; nothing here starts a process or reads a token."""
from __future__ import annotations

from typing import Any

from . import ledger, registry, state
from .manifest import Preset, consent

REAL_FACTS = ("publisher", "publisher_kind", "license", "license_note", "registry", "package", "version", "transport", "hosts", "read_only", "verified_on", "sources")


def _param_specs(preset: Preset) -> list[dict[str, str]]:
    return [{"name": p["name"], "label": p["label"], "kind": p["kind"]} for p in preset.params]


def _credential_specs(preset: Preset) -> list[dict[str, str]]:
    return [{"env": c["env"], "label": c["label"]} for c in (preset.real or {}).get("credentials", [])]


def view(preset: Preset, *, detail: bool = False) -> dict[str, Any]:
    rec = state.record(preset.id)
    st = state.status(preset, rec)
    params = (rec or {}).get("params") or {}
    modes: dict[str, Any] = {"example": consent(preset, "example"), "real": None}
    if preset.has_real:
        real = consent(preset, "real", params)
        real["params"], real["credentials"] = _param_specs(preset), _credential_specs(preset)
        real["verified"] = True
        modes["real"] = real
    reads = ledger.reads_summary(preset.id)
    out: dict[str, Any] = {
        "id": preset.id, "app": preset.app, "group": preset.group, "kind": preset.kind, "reads": preset.reads, "caution": preset.caution,
        "state": st["state"], "mode": st["mode"], "reason": st["reason"], "example": st["mode"] == "example", "modes": modes,
        "tools": preset.tools.counts(), "usage": {k: reads[k] for k in ("calls", "reads", "changes_asked", "refused", "needed_click", "last_call")},
        "probe": (rec or {}).get("probe"), "consented_at": (rec or {}).get("consented_at"), "roles": registry.roles_for(preset.id),
        "routines": list((rec or {}).get("routines", [])) if rec else [],
    }
    if detail:
        out["description"] = preset.description
        out["limitations"] = list(preset.limitations)
        out["real_facts"] = {k: preset.real[k] for k in REAL_FACTS if preset.real and k in preset.real} if preset.real else None
        out["unlisted"] = preset.tools.unlisted
        out["usage"] = {k: v for k, v in reads.items() if k != "note"}
        out["note"] = reads["note"]
    return out


def listing(role: str | None = None, group: str | None = None) -> list[dict[str, Any]]:
    presets = registry.for_role(role) if role else list(registry.all_presets().values())
    if group:
        presets = [p for p in presets if p.group == group]
    return [view(p) for p in presets]
